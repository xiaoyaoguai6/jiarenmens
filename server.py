"""
东方财富选手数据 & 大同证券投顾数据 Web API
============================================
FastAPI 服务，暴露两个数据源：
  1. 东方财富选手数据（crawl_data.db）
  2. 大同证券投顾组合数据（portfolio.db）

启动: uvicorn server:app --host 0.0.0.0 --port 8000
文档: http://localhost:8000/docs
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import sqlite3
import uuid
import time

import requests

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.storage.sqlite_storage import SQLiteStorage
from src.storage.portfolio_db import PortfolioDB
from src.utils.logger import setup_logger

logger = setup_logger()

app = FastAPI(
    title="东方财富选手 & 大同证券投顾数据 API",
    description="提供东方财富实盘大赛选手数据以及大同证券投顾组合持仓/调仓数据",
    version="1.0.0",
)

# CORS - allow all origins for external access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data directory ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CRAWL_DB = DATA_DIR / "crawl_data.db"
PORTFOLIO_DB = DATA_DIR / "portfolio.db"


# ── Helper: get storage instances ───────────────────────────────────────────
def get_crawl_storage() -> SQLiteStorage:
    if not CRAWL_DB.exists():
        raise HTTPException(503, detail="crawl_data.db 尚未创建，请先运行爬虫: python main.py")
    return SQLiteStorage(db_path=CRAWL_DB)


def get_portfolio_db() -> PortfolioDB:
    if not PORTFOLIO_DB.exists():
        raise HTTPException(503, detail="portfolio.db 尚未创建，暂无投顾数据")
    return PortfolioDB(db_path=PORTFOLIO_DB)


# ── JSON helpers ────────────────────────────────────────────────────────────
class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)


def json_dumps(data):
    return json.dumps(data, ensure_ascii=False, cls=DateTimeEncoder)


# ── Follow system ────────────────────────────────────────────────────────────
_FOLLOW_DB_INITED = False


def _init_follow_db():
    global _FOLLOW_DB_INITED
    if _FOLLOW_DB_INITED:
        return
    with sqlite3.connect(CRAWL_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS followed_players (
                zh_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    _FOLLOW_DB_INITED = True


@app.get("/api/search")
def search_players(q: str = Query("", description="搜索关键词")):
    """搜索选手（按组合名或选手ID模糊匹配）"""
    if not q.strip():
        return {"total": 0, "data": []}
    storage = get_crawl_storage()
    players = storage.load_players()
    keyword = q.strip().lower()
    matched = []
    for p in players:
        name = (p.get("name") or "").lower()
        zh_id = (p.get("zh_id") or "").lower()
        if keyword in name or keyword in zh_id:
            matched.append({
                "zh_id": p.get("zh_id"),
                "name": p.get("name", ""),
                "followers": p.get("followers", 0),
                "total_return": p.get("total_return", 0),
                "daily_return": p.get("daily_return", 0),
            })
    return {"total": len(matched), "data": matched[:50]}


@app.post("/api/follow/{zh_id}")
def follow_player(zh_id: str):
    """关注选手"""
    _init_follow_db()
    with sqlite3.connect(CRAWL_DB) as conn:
        conn.execute("INSERT OR IGNORE INTO followed_players (zh_id) VALUES (?)", (zh_id,))
    return {"ok": True, "zh_id": zh_id}


@app.delete("/api/follow/{zh_id}")
def unfollow_player(zh_id: str):
    """取消关注"""
    _init_follow_db()
    with sqlite3.connect(CRAWL_DB) as conn:
        conn.execute("DELETE FROM followed_players WHERE zh_id=?", (zh_id,))
    return {"ok": True, "zh_id": zh_id}


@app.get("/api/follow")
def list_followed():
    """获取关注列表（含选手基本信息）"""
    _init_follow_db()
    storage = get_crawl_storage()
    with sqlite3.connect(CRAWL_DB) as conn:
        rows = conn.execute("SELECT zh_id, created_at FROM followed_players ORDER BY created_at DESC").fetchall()
        followed = [{"zh_id": r[0], "followed_at": r[1]} for r in rows]
    # enrich with player data
    for f in followed:
        p = storage.load_player(f["zh_id"])
        if p:
            f["name"] = p.get("name", "")
            f["followers"] = p.get("followers", 0)
            f["total_return"] = p.get("total_return", 0)
            f["daily_return"] = p.get("daily_return", 0)
        else:
            f["name"] = ""
            f["followers"] = 0
    return {"total": len(followed), "data": followed}


@app.get("/api/follow/ids")
def list_followed_ids():
    """获取已关注选手 ID 列表（用于前端判断关注状态）"""
    _init_follow_db()
    with sqlite3.connect(CRAWL_DB) as conn:
        rows = conn.execute("SELECT zh_id FROM followed_players").fetchall()
    return {"ids": [r[0] for r in rows]}


# ── Player detail (rtV2 + ranking positions) ─────────────────────────────────

EM_API = "https://emdcspzhapi.eastmoney.com/rtV2"
EM_HEADERS_FILE = Path(__file__).parent / "config" / "em_headers.json"


def _load_em_headers() -> dict:
    h = {
        "Accept-Encoding": "gzip",
        "Content-Type": "application/json; charset=UTF-8",
        "EM-CHL": "taobao45", "EM-CT": "", "EM-OS": "Android",
        "EM-PA": "1", "EM-SL": "0", "EM-UT": "",
        "User-Agent": "okhttp/3.12.13",
        "Host": "emdcspzhapi.eastmoney.com",
    }
    if EM_HEADERS_FILE.exists():
        cfg = json.loads(EM_HEADERS_FILE.read_text(encoding="utf-8"))
        for k in ("EM-MD", "EM-GT", "EM-GV", "EM-VER", "EM-PKG"):
            if cfg.get(k):
                h[k] = cfg[k]
    return h


def _fetch_rtv2(zh_id: str) -> dict:
    """调用 rtV2 combination_detail_97 获取选手最新数据"""
    headers = _load_em_headers()
    body = {
        "args": {"reqUserid": "", "zh": zh_id},
        "clientType": "cfzq", "method": "combination_detail_97",
        "client": "android", "appKey": "eastmoney",
        "clientVersion": "10.13.5",
        "randomCode": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
    }
    r = requests.post(EM_API, json=body, headers=headers, timeout=15)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(f"API error: {j.get('message')}")
    return j["data"]


def _get_player_rankings(zh_id: str, players: list) -> list:
    """在 DB 选手数据中查找该选手在所有榜单中的排名"""
    result = []
    for rank_type in ("总榜", "年榜", "月榜", "周榜", "日榜"):
        ranked = []
        for p in players:
            ranks = p.get("ranks", {})
            if isinstance(ranks, list):
                ranks = {}
            entry = ranks.get(rank_type)
            if entry and entry.get("return") is not None:
                ranked.append((p.get("zh_id"), entry["return"]))
        ranked.sort(key=lambda x: x[1] or 0, reverse=True)
        for idx, (zid, val) in enumerate(ranked):
            if zid == zh_id:
                result.append({"rank_type": rank_type, "rank": idx + 1, "return": val})
                break
    return result


@app.get("/api/player-detail/{zh_id}")
def player_detail(zh_id: str):
    """获取选手实时详情（rtV2 API）+ 持仓 + 调仓 + 今日榜单排名"""
    storage = get_crawl_storage()

    # 1. 从 rtV2 获取实时数据
    try:
        rtv2 = _fetch_rtv2(zh_id)
    except Exception as e:
        raise HTTPException(502, detail=f"rtV2 API 调用失败: {e}")

    detail = rtv2.get("detail", {})
    positions = rtv2.get("position", [])
    trades = rtv2.get("tradeSummary", [])

    # 2. 从 DB 获取榜单排名
    all_players = storage.load_players()
    rankings = _get_player_rankings(zh_id, all_players)

    # 3. 组装返回
    return {
        "zh_id": zh_id,
        "detail": {
            "name": detail.get("zuheName") or detail.get("uidNick") or "",
            "followers": int(detail.get("concernCnt", 0)),
            "total_return": detail.get("rate"),
            "daily_return": detail.get("rateDay"),
            "return_5d": detail.get("rate5Day"),
            "return_20d": detail.get("rate20Day"),
            "return_60d": detail.get("rate60Day"),
            "return_250d": detail.get("rate250Day"),
            "net_value": detail.get("JZ"),
            "max_drawdown": detail.get("maxDrawDown"),
            "win_rate": detail.get("dealRate"),
            "days": detail.get("yxts"),
            "intro": detail.get("comment") or detail.get("uidComment") or "",
            "labels": [detail.get(k) for k in ("label1", "label2", "label3") if detail.get(k)],
        },
        "positions": [
            {
                "stock_name": p.get("__name", ""),
                "stock_code": str(p.get("__code", "")),
                "cost_price": p.get("cbj"),
                "current_price": p.get("__zxjg"),
                "profit_ratio": p.get("webYkRate"),
                "position_ratio": p.get("holdPos") or p.get("positionRateDetail"),
            }
            for p in (positions or [])
        ],
        "trades": [
            {
                "stock_name": t.get("stkName", ""),
                "trade_date": t.get("tzrq", ""),
                "buy_qty": t.get("lshj_mr", 0),
                "sell_qty": t.get("lshj_mc", 0),
            }
            for t in (trades or [])
        ],
        "rankings": rankings,
        "tendency": rtv2.get("tendency", []),
        "tendency_summary": rtv2.get("tendencySummary", {}),
        "dimensions": rtv2.get("dimensions", {}),
        "evaluation": rtv2.get("evaluation", {}),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  东方财富选手数据 (crawl_data.db)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/players")
def list_players(
    sort_by: str = Query("daily_return", description="排序字段: daily_return, total_return, followers, name"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取东方财富选手列表（含多周期收益率）"""
    storage = get_crawl_storage()
    players = storage.load_players()

    # Sort
    reverse = sort_by not in ("name", "zh_id")
    players.sort(key=lambda p: (p.get(sort_by) or 0) if not isinstance(p.get(sort_by), str) else p.get(sort_by, ""), reverse=reverse)

    total = len(players)
    page = players[offset:offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "data": page}


@app.get("/api/players/{zh_id}")
def get_player(zh_id: str):
    """获取单个选手详细信息"""
    storage = get_crawl_storage()
    player = storage.load_player(zh_id)
    if not player:
        raise HTTPException(404, detail=f"选手 {zh_id} 不存在")
    return player


@app.get("/api/players/{zh_id}/positions")
def get_player_positions(
    zh_id: str,
    crawl_date: Optional[str] = Query(None, description="日期 (YYYY-MM-DD)，默认最新"),
):
    """获取选手持仓数据"""
    storage = get_crawl_storage()
    positions = storage.load_positions(zh_id, crawl_date)
    return {"zh_id": zh_id, "count": len(positions), "data": positions}


@app.get("/api/players/{zh_id}/trades")
def get_player_trades(
    zh_id: str,
    crawl_date: Optional[str] = Query(None, description="日期 (YYYY-MM-DD)，默认最新"),
):
    """获取选手调仓记录"""
    storage = get_crawl_storage()
    trades = storage.load_trades(zh_id, crawl_date)
    return {"zh_id": zh_id, "count": len(trades), "data": trades}


@app.get("/api/positions/top-holdings")
def top_holdings(
    top_n: int = Query(20, ge=1, le=100, description="返回前N只股票"),
    crawl_date: Optional[str] = Query(None, description="日期"),
):
    """获取选手持仓最多的股票排行"""
    storage = get_crawl_storage()
    return {"data": storage.get_top_holdings(top_n, crawl_date)}


@app.get("/api/positions/distribution")
def position_distribution(crawl_date: Optional[str] = Query(None, description="日期")):
    """获取选手仓位分布统计"""
    storage = get_crawl_storage()
    return storage.get_position_distribution(crawl_date)


@app.get("/api/players/top-performers")
def top_performers(
    top_n: int = Query(10, ge=1, le=100, description="返回前N名"),
):
    """获取当日盈利最高的选手"""
    storage = get_crawl_storage()
    return {"data": storage.get_top_performers(top_n)}


@app.get("/api/positions/all")
def all_positions(crawl_date: Optional[str] = Query(None, description="日期")):
    """获取所有选手的持仓数据"""
    storage = get_crawl_storage()
    return {"data": storage.get_all_positions(crawl_date)}


# ══════════════════════════════════════════════════════════════════════════════
#  榜单排名 (5种收益榜单)
# ══════════════════════════════════════════════════════════════════════════════

RANK_LABELS = {"总榜", "年榜", "月榜", "周榜", "日榜"}


@app.get("/api/rankings/{rank_type}")
def get_ranking(rank_type: str):
    """获取指定榜单排名（总榜/年榜/月榜/周榜/日榜），按收益率降序排列"""
    if rank_type not in RANK_LABELS:
        raise HTTPException(400, detail=f"榜单类型必须是: {', '.join(sorted(RANK_LABELS))}")

    storage = get_crawl_storage()
    players = storage.load_players()

    ranked = []
    for p in players:
        ranks = p.get("ranks", {})
        if isinstance(ranks, list):
            ranks = {}
        entry = ranks.get(rank_type)
        if entry and entry.get("return") is not None:
            ranked.append({
                "zh_id": p.get("zh_id"),
                "name": p.get("name", ""),
                "followers": p.get("followers", 0),
                "return": entry["return"],
            })

    ranked.sort(key=lambda x: x["return"] or 0, reverse=True)
    return {"rank_type": rank_type, "total": len(ranked), "data": ranked}


# ══════════════════════════════════════════════════════════════════════════════
#  榜单排名 HTML 页面
# ══════════════════════════════════════════════════════════════════════════════

_RANKINGS_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>公开实盘排行榜</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f0f2f5; color: #1f2937; padding: 20px; }
  .container { max-width: 960px; margin: 0 auto; }
  .nav { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
  .nav h1 { font-size: 22px; color: #1e3a8a; margin: 0; }
  .nav a { text-decoration: none; color: #1e3a8a; font-size: 14px; padding: 6px 14px;
           border: 1px solid #1e3a8a; border-radius: 6px; }
  .nav a:hover { background: #eff6ff; }
  .search-box { display: flex; gap: 6px; margin-bottom: 16px; }
  .search-box input { flex: 1; padding: 8px 14px; border: 1px solid #d1d5db; border-radius: 6px;
                      font-size: 14px; outline: none; }
  .search-box input:focus { border-color: #1e3a8a; box-shadow: 0 0 0 2px rgba(30,58,138,.1); }
  .search-box button { padding: 8px 18px; border: 1px solid #1e3a8a; border-radius: 6px;
                       background: #1e3a8a; color: #fff; font-size: 14px; cursor: pointer; }
  .search-box button:hover { background: #2563eb; }
  .search-results { display: none; }
  .search-mode .tabs, .search-mode .pagination, .search-mode .rank-table { display: none; }
  .search-mode .search-results { display: block; }
  .tabs { display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }
  .tab { padding: 8px 20px; border: 1px solid #d1d5db; border-radius: 6px;
         background: #fff; cursor: pointer; font-size: 14px; color: #374151;
         transition: all .15s; }
  .tab:hover { background: #eff6ff; }
  .tab.active { background: #1e3a8a; color: #fff; border-color: #1e3a8a; }
  .info { font-size: 13px; color: #6b7280; margin-bottom: 10px; }
  .pagination { display: flex; justify-content: center; align-items: center;
                gap: 10px; margin: 16px 0; font-size: 14px; }
  .pagination button { padding: 6px 14px; border: 1px solid #d1d5db;
                       border-radius: 4px; background: #fff; cursor: pointer; }
  .pagination button:disabled { opacity: .4; cursor: not-allowed; }
  .pagination button:hover:not(:disabled) { background: #eff6ff; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  th, td { padding: 10px 12px; text-align: left; font-size: 14px; }
  th { background: #f8fafc; color: #475569; font-weight: 600;
       border-bottom: 2px solid #e2e8f0; }
  td { border-bottom: 1px solid #f1f5f9; }
  tr:hover td { background: #f8fafc; }
  .rank-num { font-weight: 600; color: #1e3a8a; width: 36px; }
  .positive { color: #dc2626; }
  .negative { color: #16a34a; }
  .zero { color: #9ca3af; }
  .fans { color: #6b7280; font-size: 13px; }
  .loading { text-align: center; padding: 40px; color: #6b7280; }
  .player-link { color: #1e3a8a; text-decoration: none; font-weight: 500; cursor: pointer; }
  .player-link:hover { text-decoration: underline; color: #2563eb; }
  .follow-btn { padding: 3px 10px; border-radius: 4px; border: 1px solid #d1d5db;
                font-size: 12px; cursor: pointer; background: #fff; color: #374151; }
  .follow-btn:hover { background: #eff6ff; }
  .follow-btn.followed { background: #dbeafe; color: #1e3a8a; border-color: #1e3a8a; }
  .search-hint { color: #6b7280; font-size: 13px; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <h1>📊 公开实盘排行榜</h1>
    <a href="/follow">❤️ 关注列表</a>
  </div>
  <div class="search-box">
    <input id="searchInput" placeholder="搜索选手名或组合ID..." onkeydown="if(event.key==='Enter') doSearch()">
    <button onclick="doSearch()">搜索</button>
  </div>
  <div class="tabs" id="tabs"></div>
  <div id="searchMode" class="search-results"></div>
  <div class="info" id="info"></div>
  <div id="loading" class="loading">加载中...</div>
  <table id="table" class="rank-table" style="display:none">
    <thead><tr><th>#</th><th>组合名</th><th>选手名</th><th>粉丝数</th><th>收益率</th><th>操作</th></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="pagination" id="pagination" style="display:none">
    <button id="prevBtn" onclick="goPage(-1)">上一页</button>
    <span id="pageInfo"></span>
    <button id="nextBtn" onclick="goPage(1)">下一页</button>
  </div>
</div>
<script>
const RANK_TYPES = ['总榜', '年榜', '月榜', '周榜', '日榜'];
const PAGE_SIZE = 20;
let allData = {};
let currentType = '总榜';
let currentPage = 0;
let followedSet = new Set();

// load followed ids
fetch('/api/follow/ids').then(r=>r.json()).then(d=>{ followedSet = new Set(d.ids); render(); });

// tabs
const tabsEl = document.getElementById('tabs');
RANK_TYPES.forEach(t => {
  const btn = document.createElement('button');
  btn.className = 'tab' + (t === currentType ? ' active' : '');
  btn.textContent = t;
  btn.onclick = () => switchTab(t);
  tabsEl.appendChild(btn);
});

function switchTab(type) {
  currentType = type;
  currentPage = 0;
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.textContent === type));
  document.getElementById('searchMode').style.display = 'none';
  document.getElementById('table').style.display = '';
  document.getElementById('pagination').style.display = '';
  render();
}

async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const searchMode = document.getElementById('searchMode');
  searchMode.style.display = 'block';
  document.getElementById('table').style.display = 'none';
  document.getElementById('pagination').style.display = 'none';
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.getElementById('info').textContent = '搜索: ' + q;

  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q));
    const d = await r.json();
    if (d.total === 0) {
      searchMode.innerHTML = '<div class="search-hint">未找到匹配 "' + esc(q) + '" 的选手</div>';
      return;
    }
    let html = '<div class="search-hint">找到 ' + d.total + ' 个匹配结果（最多显示50条）</div>';
    html += '<table><thead><tr><th>组合名</th><th>选手名</th><th>粉丝数</th><th>总收益</th><th>日收益</th><th>操作</th></tr></thead><tbody>';
    d.data.forEach(p => {
      const isFollowed = followedSet.has(p.zh_id);
      const trCls = p.total_return > 0 ? 'positive' : p.total_return < 0 ? 'negative' : 'zero';
      const drCls = p.daily_return > 0 ? 'positive' : p.daily_return < 0 ? 'negative' : 'zero';
      html += '<tr><td><a class="player-link" href="/player/' + encodeURIComponent(p.zh_id) + '">' + esc(p.name||'--') + '</a></td>'
        + '<td class="fans">' + esc(p.zh_id) + '</td>'
        + '<td>' + (p.followers||0).toLocaleString() + '</td>'
        + '<td class="' + trCls + '">' + (p.total_return||0).toFixed(2) + '%</td>'
        + '<td class="' + drCls + '">' + (p.daily_return||0).toFixed(2) + '%</td>'
        + '<td><button class="follow-btn' + (isFollowed ? ' followed' : '') + '" data-zh="' + p.zh_id + '" onclick="toggleFollow(this)">' + (isFollowed ? '已关注' : '+ 关注') + '</button></td></tr>';
    });
    html += '</tbody></table>';
    searchMode.innerHTML = html;
  } catch(e) {
    searchMode.innerHTML = '<div style="color:#dc2626">搜索失败: ' + e.message + '</div>';
  }
}

async function loadData() {
  const loading = document.getElementById('loading');
  const table = document.getElementById('table');
  const pagination = document.getElementById('pagination');
  try {
    const res = await Promise.all(RANK_TYPES.map(t =>
      fetch('/api/rankings/' + encodeURIComponent(t)).then(r => r.json())
    ));
    RANK_TYPES.forEach((t, i) => { allData[t] = res[i].data; });
    loading.style.display = 'none';
    table.style.display = '';
    pagination.style.display = '';
    render();
  } catch (e) {
    loading.textContent = '加载失败: ' + e.message;
  }
}

function render() {
  const data = allData[currentType] || [];
  const total = data.length;
  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
  if (currentPage >= totalPages) currentPage = totalPages - 1;
  const start = currentPage * PAGE_SIZE;
  const page = data.slice(start, start + PAGE_SIZE);

  document.getElementById('info').textContent = currentType + ' — 共 ' + total + ' 名选手';

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  page.forEach((p, i) => {
    const rank = start + i + 1;
    const r = p.return;
    const cls = r > 0 ? 'positive' : r < 0 ? 'negative' : 'zero';
    const sign = r > 0 ? '+' : '';
    const isFollowed = followedSet.has(p.zh_id);
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="rank-num">' + rank + '</td>'
      + '<td><a class="player-link" href="/player/' + encodeURIComponent(p.zh_id) + '">' + esc(p.name) + '</a></td>'
      + '<td class="fans">' + esc(p.zh_id) + '</td>'
      + '<td class="fans">' + p.followers.toLocaleString() + '</td>'
      + '<td class="' + cls + '">' + sign + r.toFixed(2) + '%</td>'
      + '<td><button class="follow-btn' + (isFollowed ? ' followed' : '') + '" data-zh="' + p.zh_id + '" onclick="toggleFollow(this)">' + (isFollowed ? '已关注' : '+ 关注') + '</button></td>';
    tbody.appendChild(tr);
  });

  document.getElementById('pageInfo').textContent = '第 ' + (currentPage + 1) + '/' + totalPages + ' 页';
  document.getElementById('prevBtn').disabled = currentPage <= 0;
  document.getElementById('nextBtn').disabled = currentPage >= totalPages - 1;
}

function goPage(delta) {
  const data = allData[currentType] || [];
  const totalPages = Math.ceil(data.length / PAGE_SIZE) || 1;
  const newPage = currentPage + delta;
  if (newPage < 0 || newPage >= totalPages) return;
  currentPage = newPage;
  render();
}

async function toggleFollow(btn) {
  const zh = btn.dataset.zh;
  const isFollowed = followedSet.has(zh);
  try {
    if (isFollowed) {
      await fetch('/api/follow/' + encodeURIComponent(zh), { method: 'DELETE' });
      followedSet.delete(zh);
      btn.textContent = '+ 关注';
      btn.classList.remove('followed');
    } else {
      await fetch('/api/follow/' + encodeURIComponent(zh), { method: 'POST' });
      followedSet.add(zh);
      btn.textContent = '已关注';
      btn.classList.add('followed');
    }
  } catch(e) { alert('操作失败'); }
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

loadData();
</script>
</body>
</html>"""


@app.get("/rankings", response_class=HTMLResponse)
def rankings_page():
    return _RANKINGS_HTML


# ══════════════════════════════════════════════════════════════════════════════
#  关注列表 HTML 页面
# ══════════════════════════════════════════════════════════════════════════════

_FOLLOW_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关注列表</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f0f2f5; color: #1f2937; padding: 20px; }
  .container { max-width: 800px; margin: 0 auto; }
  .nav { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
  .nav h1 { font-size: 22px; color: #1e3a8a; margin: 0; }
  .nav a { text-decoration: none; color: #1e3a8a; font-size: 14px; padding: 6px 14px;
           border: 1px solid #1e3a8a; border-radius: 6px; }
  .nav a:hover { background: #eff6ff; }
  .info { font-size: 13px; color: #6b7280; margin-bottom: 10px; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  th, td { padding: 10px 14px; text-align: left; font-size: 14px; }
  th { background: #f8fafc; color: #475569; font-weight: 600;
       border-bottom: 2px solid #e2e8f0; }
  td { border-bottom: 1px solid #f1f5f9; }
  tr:hover td { background: #f8fafc; }
  .player-link { color: #1e3a8a; text-decoration: none; font-weight: 500; }
  .player-link:hover { text-decoration: underline; }
  .follow-btn { padding: 3px 10px; border-radius: 4px; border: 1px solid #dc2626;
                font-size: 12px; cursor: pointer; background: #fff; color: #dc2626; }
  .follow-btn:hover { background: #fef2f2; }
  .positive { color: #dc2626; } .negative { color: #16a34a; } .zero { color: #9ca3af; }
  .loading { text-align: center; padding: 40px; color: #6b7280; }
  .empty { text-align: center; padding: 40px; color: #9ca3af; font-size: 15px; }
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <h1>❤️ 关注列表</h1>
    <a href="/rankings">📊 排行榜</a>
  </div>
  <div class="info" id="info"></div>
  <div id="loading" class="loading">加载中...</div>
  <table id="table" style="display:none">
    <thead><tr><th>组合名</th><th>选手名</th><th>粉丝数</th><th>总收益</th><th>日收益</th><th>操作</th></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">还没有关注任何选手，去 <a href="/rankings">排行榜</a> 看看吧</div>
</div>
<script>
async function load() {
  const loading = document.getElementById('loading');
  const table = document.getElementById('table');
  const empty = document.getElementById('empty');
  try {
    const r = await fetch('/api/follow');
    const d = await r.json();
    loading.style.display = 'none';
    document.getElementById('info').textContent = '共关注 ' + d.total + ' 名选手';
    if (d.total === 0) { empty.style.display = ''; return; }
    table.style.display = '';
    const tbody = document.getElementById('tbody');
    d.data.forEach(p => {
      const tr = document.createElement('tr');
      const dr = p.daily_return || 0;
      const drCls = dr > 0 ? 'positive' : dr < 0 ? 'negative' : 'zero';
      const trCls = p.total_return > 0 ? 'positive' : p.total_return < 0 ? 'negative' : 'zero';
      tr.innerHTML = '<td><a class="player-link" href="/player/' + encodeURIComponent(p.zh_id) + '">' + esc(p.name||'--') + '</a></td>'
        + '<td class="fans">' + esc(p.zh_id) + '</td>'
        + '<td>' + (p.followers||0).toLocaleString() + '</td>'
        + '<td class="' + trCls + '">' + (p.total_return||0).toFixed(2) + '%</td>'
        + '<td class="' + drCls + '">' + dr.toFixed(2) + '%</td>'
        + '<td><button class="follow-btn" onclick="unfollow(\'' + p.zh_id + '\', this)">取消关注</button></td>';
      tbody.appendChild(tr);
    });
  } catch(e) { loading.textContent = '加载失败: ' + e.message; }
}
async function unfollow(zh, btn) {
  try {
    await fetch('/api/follow/' + encodeURIComponent(zh), { method: 'DELETE' });
    btn.closest('tr').remove();
    location.reload();
  } catch(e) { alert('操作失败'); }
}
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
load();
</script>
</body>
</html>"""


@app.get("/follow", response_class=HTMLResponse)
def follow_page():
    return _FOLLOW_HTML


# ══════════════════════════════════════════════════════════════════════════════
#  选手详情 HTML 页面
# ══════════════════════════════════════════════════════════════════════════════

_PLAYER_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>选手详情</title>
<style>
  :root {
    --primary: #1e3a8a;
    --primary-light: #3b82f6;
    --primary-bg: #eff6ff;
    --bg: #f0f4f9;
    --card: #ffffff;
    --text: #1e293b;
    --text-secondary: #64748b;
    --border: #e2e8f0;
    --success: #16a34a;
    --danger: #dc2626;
    --warning: #d97706;
    --radius: 12px;
    --shadow: 0 1px 4px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: var(--bg); color: var(--text); padding: 24px; }
  .container { max-width: 1000px; margin: 0 auto; }

  /* Nav */
  .nav { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
  .nav-back { text-decoration: none; color: var(--text-secondary); font-size: 14px;
              padding: 6px 14px; border: 1px solid var(--border); border-radius: 8px;
              transition: all .15s; }
  .nav-back:hover { background: var(--primary-bg); color: var(--primary); }
  .nav-title { font-size: 20px; font-weight: 700; color: var(--text); flex: 1; }
  .nav-links { display: flex; gap: 8px; }
  .nav-links a { text-decoration: none; color: var(--text-secondary); font-size: 13px;
                 padding: 6px 12px; border: 1px solid var(--border); border-radius: 8px; }
  .nav-links a:hover { background: var(--primary-bg); color: var(--primary); }

  /* Loading / Error */
  .loading, .error { text-align: center; padding: 60px 20px; color: var(--text-secondary); font-size: 15px; }
  .error { color: var(--danger); }

  /* Cards */
  .card { background: var(--card); border-radius: var(--radius); padding: 20px 24px;
          margin-bottom: 16px; box-shadow: var(--shadow); }
  .card-title { font-size: 13px; font-weight: 600; color: var(--text-secondary);
                text-transform: uppercase; letter-spacing: .5px; margin-bottom: 16px;
                display: flex; align-items: center; gap: 6px; }

  /* Metrics grid */
  .metrics { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
  .metric { padding: 14px; border-radius: 10px; background: #f8fafc; text-align: center; }
  .metric .label { font-size: 11px; color: var(--text-secondary); margin-bottom: 4px; }
  .metric .value { font-size: 18px; font-weight: 700; }
  .metric .sub { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }

  /* Analysis scores */
  .scores { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 12px; }
  .score-item { text-align: center; padding: 12px 8px; border-radius: 10px; background: #f8fafc; }
  .score-item .ring { width: 56px; height: 56px; border-radius: 50%; margin: 0 auto 6px;
                      display: flex; align-items: center; justify-content: center;
                      font-size: 16px; font-weight: 700; color: #fff; }
  .score-item .label { font-size: 11px; color: var(--text-secondary); }
  .score-item .sub-label { font-size: 9px; color: #94a3b8; margin-top: 2px; }

  /* Chart */
  .chart-wrap { position: relative; width: 100%; height: 260px; }
  .chart-wrap canvas { width: 100%; height: 100%; border-radius: 8px; }
  .chart-legend { display: flex; gap: 20px; justify-content: center; margin-top: 10px; font-size: 12px; }
  .chart-legend span { display: flex; align-items: center; gap: 4px; }
  .chart-legend .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

  /* Ranking badges */
  .rankings-wrap { display: flex; gap: 8px; flex-wrap: wrap; }
  .rank-badge { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px;
                border-radius: 20px; font-size: 12px; font-weight: 500;
                background: var(--primary-bg); color: var(--primary);
                border: 1px solid rgba(30,58,138,.15); }

  /* Tables */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f1f5f9; white-space: nowrap; }
  th { color: var(--text-secondary); font-weight: 600; font-size: 11px;
       text-transform: uppercase; letter-spacing: .3px; background: #f8fafc; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f8fafc; }

  /* Colors */
  .c-positive { color: var(--danger); }
  .c-negative { color: var(--success); }
  .c-zero { color: var(--text-secondary); }
  .c-primary { color: var(--primary); }

  /* Tags */
  .tag { display: inline-block; padding: 2px 8px; border-radius: 4px;
         font-size: 11px; background: #f1f5f9; color: var(--text-secondary); margin: 1px; }

  /* Responsive */
  @media (max-width: 640px) {
    body { padding: 12px; }
    .metrics { grid-template-columns: repeat(3, 1fr); }
    .scores { grid-template-columns: repeat(3, 1fr); }
    .nav-title { font-size: 16px; }
  }
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a class="nav-back" href="javascript:history.back()">← 返回</a>
    <span class="nav-title" id="playerName">选手详情</span>
    <span class="nav-links">
      <a href="/rankings">排行榜</a>
      <a href="/follow">关注</a>
    </span>
  </div>
  <div id="loading" class="loading"><div style="font-size:24px;margin-bottom:8px">⏳</div>加载中...</div>
  <div id="content" style="display:none"></div>
</div>
<script>
const zhId = location.pathname.split('/').pop();

async function load() {
  const loading = document.getElementById('loading');
  const content = document.getElementById('content');
  try {
    const r = await fetch('/api/player-detail/' + encodeURIComponent(zhId));
    if (!r.ok) { loading.className = 'error'; loading.textContent = '❌ 选手不存在或API错误'; return; }
    const d = await r.json();
    loading.style.display = 'none';
    content.style.display = '';

    const det = d.detail || {};
    document.getElementById('playerName').textContent = '👤 ' + (det.name || zhId);

    let html = '';

    // ── Key Metrics ──
    html += '<div class="card"><div class="card-title">📊 关键指标</div><div class="metrics">';
    const metrics = [
      ['总收益率', fmtPct(det.total_return), ''],
      ['日收益率', fmtPct(det.daily_return), ''],
      ['净值', det.net_value != null ? Number(det.net_value).toFixed(4) : '--', ''],
      ['最大回撤', det.max_drawdown != null ? Number(det.max_drawdown).toFixed(2) + '%' : '--', '越小越好'],
      ['日胜率', det.win_rate != null ? Number(det.win_rate).toFixed(1) + '%' : '--', ''],
      ['运行天数', det.days ? Number(det.days).toLocaleString() : '--', ''],
      ['粉丝数', det.followers ? Number(det.followers).toLocaleString() : '0', ''],
      ['5日收益', fmtPct(det.return_5d), ''],
      ['20日收益', fmtPct(det.return_20d), ''],
      ['60日收益', fmtPct(det.return_60d), ''],
      ['250日收益', fmtPct(det.return_250d), ''],
    ];
    metrics.forEach(m => {
      html += '<div class="metric"><div class="label">' + m[0] + '</div><div class="value">' + m[1] + '</div>';
      if (m[2]) html += '<div class="sub">' + m[2] + '</div>';
      html += '</div>';
    });
    html += '</div></div>';

    // ── Analysis Scores (Hexagon Radar Chart) ──
    const dim = d.dimensions || {};
    const ev = d.evaluation || {};
    const scoreItems = [
      { label: '收益能力', key: 'profitRateScore' },
      { label: '日胜率', key: 'dayWinRateScore' },
      { label: '风控水平', key: 'maxDrawdownScore' },
      { label: '夏普比', key: 'sharpeRatioScore' },
      { label: '分散度', key: 'investmentDispersionScore' },
      { label: '综合评分', key: 'score' },
    ];
    const hasScores = scoreItems.some(s => ev[s.key] != null);
    if (hasScores) {
      html += '<div class="card"><div class="card-title">🎯 分析评分（六维图）</div>';
      html += '<div style="display:flex;flex-wrap:wrap;gap:20px;align-items:center">';
      html += '<div style="flex:1;min-width:280px;max-width:400px"><canvas id="radarChart" style="width:100%;height:280px"></canvas></div>';
      html += '<div style="flex:0 0 auto;font-size:13px;color:var(--text-secondary)">';
      scoreItems.forEach(s => {
        const v = ev[s.key] != null ? Math.round(Number(ev[s.key])) : null;
        html += '<div style="display:flex;align-items:center;gap:8px;padding:3px 0">'
          + '<span style="width:10px;height:10px;border-radius:2px;background:var(--primary)"></span>'
          + '<span>' + s.label + '</span>'
          + '<span style="font-weight:600;color:var(--text)">' + (v != null ? v + '分' : '--') + '</span></div>';
      });
      html += '</div></div></div>';
    }

    // ── Return Rate Trend Chart ──
    const tendency = d.tendency || [];
    if (tendency.length > 1) {
      html += '<div class="card"><div class="card-title">📈 收益率走势</div>';
      html += '<div class="chart-wrap"><canvas id="trendChart"></canvas></div>';
      html += '<div class="chart-legend">'
        + '<span><span class="dot" style="background:var(--primary)"></span> 组合收益率</span>'
        + '<span><span class="dot" style="background:#f59e0b"></span> 基准指数</span>'
        + '</div></div>';
    }

    // ── Today's Rankings ──
    if (d.rankings && d.rankings.length) {
      html += '<div class="card"><div class="card-title">🏆 今日榜单排名</div><div class="rankings-wrap">';
      d.rankings.forEach(rk => {
        const sign = rk.return > 0 ? '+' : '';
        html += '<span class="rank-badge">' + esc(rk.rank_type) + ' 第 ' + rk.rank + ' 名 (' + sign + rk.return.toFixed(2) + '%)</span>';
      });
      html += '</div></div>';
    }

    // ── Tendency Summary ──
    const ts = d.tendency_summary || {};
    if (ts.beatIndex != null) {
      html += '<div class="card"><div class="card-title">📊 跑赢指数</div><div class="metrics" style="grid-template-columns:repeat(3,1fr)">';
      html += '<div class="metric"><div class="label">累计收益</div><div class="value">' + fmtPct(ts.profit) + '</div></div>';
      html += '<div class="metric"><div class="label">跑赢指数</div><div class="value c-primary">' + (ts.beatIndex != null ? ts.beatIndex + '%' : '--') + '</div></div>';
      html += '<div class="metric"><div class="label">跑赢概率</div><div class="value c-primary">' + (ts.beatRate != null ? ts.beatRate + '%' : '--') + '</div></div>';
      html += '</div></div>';
    }

    // ── Positions ──
    const positions = d.positions || [];
    html += '<div class="card"><div class="card-title">📦 持仓 (' + positions.length + ')</div>';
    if (positions.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>股票</th><th>代码</th><th>成本价</th><th>现价</th><th>盈亏</th><th>仓位</th></tr></thead><tbody>';
      positions.forEach(p => {
        const pr = p.profit_ratio;
        const cls = pr > 0 ? 'c-positive' : pr < 0 ? 'c-negative' : 'c-zero';
        html += '<tr><td><strong>' + esc(p.stock_name) + '</strong></td><td>' + esc(p.stock_code) + '</td>'
          + '<td>' + (p.cost_price != null ? Number(p.cost_price).toFixed(2) : '--') + '</td>'
          + '<td>' + (p.current_price != null ? Number(p.current_price).toFixed(2) : '--') + '</td>'
          + '<td class="' + cls + '">' + (pr != null ? (pr > 0 ? '+' : '') + Number(pr).toFixed(2) + '%' : '--') + '</td>'
          + '<td>' + (p.position_ratio != null ? Number(p.position_ratio).toFixed(1) + '%' : '--') + '</td></tr>';
      });
      html += '</tbody></table></div>';
    } else { html += '<div style="color:var(--text-secondary);padding:8px 0">暂无持仓数据</div>'; }
    html += '</div>';

    // ── Trades ──
    const trades = d.trades || [];
    html += '<div class="card"><div class="card-title">📋 调仓记录 (' + trades.length + ')</div>';
    if (trades.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>股票</th><th>日期</th><th>方向</th></tr></thead><tbody>';
      trades.forEach(t => {
        const dir = t.buy_qty > 0 ? '买入' : t.sell_qty > 0 ? '卖出' : '--';
        const dirCls = t.buy_qty > 0 ? 'c-positive' : t.sell_qty > 0 ? 'c-negative' : '';
        const qty = t.buy_qty > 0 ? t.buy_qty : t.sell_qty > 0 ? t.sell_qty : '--';
        html += '<tr><td><strong>' + esc(t.stock_name) + '</strong></td><td>' + esc(t.trade_date) + '</td>'
          + '<td class="' + dirCls + '">' + dir + ' ' + qty + '</td></tr>';
      });
      html += '</tbody></table></div>';
    } else { html += '<div style="color:var(--text-secondary);padding:8px 0">暂无调仓记录</div>'; }
    html += '</div>';

    content.innerHTML = html;

    // ── Draw chart ──
    if (tendency.length > 1) {
      drawChart(tendency);
    }
    // ── Draw radar ──
    if (hasScores) {
      // need to wait for DOM to render the canvas
      setTimeout(() => drawRadarChart(ev), 50);
    }
  } catch(e) { loading.className = 'error'; loading.textContent = '❌ 加载失败: ' + e.message; }
}

function drawChart(data) {
  const canvas = document.getElementById('trendChart');
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = (rect.width || 900) * dpr;
  canvas.height = 260 * dpr;
  canvas.style.width = (rect.width || 900) + 'px';
  canvas.style.height = '260px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const W = rect.width || 900, H = 260;
  const pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const cw = W - pad.left - pad.right, ch = H - pad.top - pad.bottom;

  // Parse data & sort by date ascending (oldest first, left to right)
  let points = data.map(d => ({
    date: d.yk_date || '',
    total: parseFloat(d.totalRate) || 0,
    index: parseFloat(d.indexRate) || 0,
  }));
  points.sort((a, b) => a.date.localeCompare(b.date));

  // Y-axis: start from 0 (or lower if data goes negative)
  const allVals = points.flatMap(p => [p.total, p.index]);
  const dataMin = Math.min(...allVals, 0);
  const dataMax = Math.max(...allVals);
  const yMin = Math.min(0, dataMin);
  const yMax = dataMax <= 0 ? 10 : Math.max(dataMax, dataMax * 0.05 + dataMax);
  const yRange = yMax - yMin || 1;

  const xStep = cw / (points.length - 1 || 1);

  function xPos(i) { return pad.left + i * xStep; }
  function yPos(v) { return pad.top + ch - ((v - yMin) / yRange) * ch; }

  // Grid lines
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 1;
  const gridCount = 5;
  for (let i = 0; i <= gridCount; i++) {
    const y = pad.top + (ch / gridCount) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
    const val = yMax - (yRange / gridCount) * i;
    ctx.fillStyle = '#94a3b8'; ctx.font = '11px sans-serif'; ctx.textAlign = 'right';
    ctx.fillText(val.toFixed(1) + '%', pad.left - 6, y + 4);
  }

  // Zero line
  if (yMin < 0 && yMax > 0) {
    const y0 = yPos(0);
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(pad.left, y0); ctx.lineTo(W - pad.right, y0); ctx.stroke();
    ctx.setLineDash([]);
  }

  // Draw total line
  ctx.strokeStyle = '#1e3a8a';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => { i === 0 ? ctx.moveTo(xPos(i), yPos(p.total)) : ctx.lineTo(xPos(i), yPos(p.total)); });
  ctx.stroke();

  // Draw index line
  ctx.strokeStyle = '#f59e0b';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  points.forEach((p, i) => { i === 0 ? ctx.moveTo(xPos(i), yPos(p.index)) : ctx.lineTo(xPos(i), yPos(p.index)); });
  ctx.stroke();
  ctx.setLineDash([]);

  // X labels (show first, middle, last)
  ctx.fillStyle = '#94a3b8'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
  const labelIndices = [0, Math.floor(points.length / 2), points.length - 1];
  labelIndices.forEach(i => {
    const dateStr = points[i].date || '';
    const label = dateStr.length >= 8 ? dateStr.slice(2) : dateStr;
    ctx.fillText(label, xPos(i), H - pad.bottom + 16);
  });
}

function drawRadarChart(ev) {
  const canvas = document.getElementById('radarChart');
  if (!canvas) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = rect.width || 320, h = 280;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const labels = ['收益能力', '日胜率', '风控水平', '夏普比', '分散度', '综合评分'];
  const keys = ['profitRateScore', 'dayWinRateScore', 'maxDrawdownScore', 'sharpeRatioScore', 'investmentDispersionScore', 'score'];
  const values = keys.map(k => ev[k] != null ? Math.min(Number(ev[k]), 100) / 100 : 0);

  const cx = w * 0.42, cy = h * 0.5, r = Math.min(cx, cy) * 0.7;
  const levels = 5;
  const angleStep = (Math.PI * 2) / labels.length;
  // rotate so first point is at top
  const rot = -Math.PI / 2;

  function getPoint(i, radius) {
    return {
      x: cx + radius * Math.cos(rot + angleStep * i),
      y: cy + radius * Math.sin(rot + angleStep * i),
    };
  }

  // Background grid
  for (let lv = 1; lv <= levels; lv++) {
    const radius = (r / levels) * lv;
    ctx.beginPath();
    for (let i = 0; i <= labels.length; i++) {
      const p = getPoint(i % labels.length, radius);
      i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1; ctx.stroke();
  }

  // Axis lines
  for (let i = 0; i < labels.length; i++) {
    const p = getPoint(i, r);
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(p.x, p.y);
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1; ctx.stroke();

    // Labels
    const lp = getPoint(i, r + 22);
    ctx.fillStyle = '#475569'; ctx.font = '11px -apple-system, "PingFang SC", sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(labels[i], lp.x, lp.y);
  }

  // Data polygon
  ctx.beginPath();
  for (let i = 0; i <= labels.length; i++) {
    const idx = i % labels.length;
    const radius = r * values[idx];
    const p = getPoint(idx, radius);
    i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
  }
  ctx.closePath();
  ctx.fillStyle = 'rgba(30, 58, 138, 0.15)';
  ctx.fill();
  ctx.strokeStyle = '#1e3a8a'; ctx.lineWidth = 2; ctx.stroke();

  // Data points
  for (let i = 0; i < labels.length; i++) {
    const radius = r * values[i];
    const p = getPoint(i, radius);
    ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#1e3a8a'; ctx.fill();
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
  }
}

function fmtPct(v) {
  if (v == null) return '--';
  const n = Number(v);
  const cls = n > 0 ? 'c-positive' : n < 0 ? 'c-negative' : 'c-zero';
  const sign = n > 0 ? '+' : '';
  return '<span class="' + cls + '">' + sign + n.toFixed(2) + '%</span>';
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

load();
</script>
</body>
</html>"""


@app.get("/player/{zh_id}", response_class=HTMLResponse)
def player_page(zh_id: str):
    return _PLAYER_HTML


# ══════════════════════════════════════════════════════════════════════════════
#  大同证券投顾数据 (portfolio.db)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/portfolios")
def list_portfolios():
    """获取所有投顾组合列表"""
    db = get_portfolio_db()
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT p.id, p.name, p.advisor, p.total_assets, p.total_return,
                   p.daily_profit, p.snapshot_time,
                   (SELECT COUNT(*) FROM positions WHERE portfolio_id = p.id) as pos_count,
                   (SELECT COUNT(*) FROM trades WHERE portfolio_id = p.id) as trade_count
            FROM portfolios p
            ORDER BY p.id
        """).fetchall()
        portfolios = [dict(r) for r in rows]
        return {"total": len(portfolios), "data": portfolios}


@app.get("/api/portfolios/{pid}")
def get_portfolio(pid: int):
    """获取单个投顾组合概况"""
    db = get_portfolio_db()
    portfolio = db.get_portfolio(pid)
    if not portfolio:
        raise HTTPException(404, detail=f"组合 #{pid} 不存在")
    return portfolio


@app.get("/api/portfolios/{pid}/positions")
def get_portfolio_positions(pid: int):
    """获取投顾组合持仓"""
    db = get_portfolio_db()
    portfolio = db.get_portfolio(pid)
    if not portfolio:
        raise HTTPException(404, detail=f"组合 #{pid} 不存在")
    positions = db.get_positions(pid)
    return {"portfolio_id": pid, "portfolio_name": portfolio.get("name"), "count": len(positions), "data": positions}


@app.get("/api/portfolios/{pid}/trades")
def get_portfolio_trades(pid: int, limit: int = Query(20, ge=1, le=200)):
    """获取投顾组合调仓记录"""
    db = get_portfolio_db()
    portfolio = db.get_portfolio(pid)
    if not portfolio:
        raise HTTPException(404, detail=f"组合 #{pid} 不存在")
    trades = db.get_trades(pid, limit)
    return {"portfolio_id": pid, "portfolio_name": portfolio.get("name"), "count": len(trades), "data": trades}


@app.get("/api/portfolios/{pid}/identified")
def get_portfolio_identified(pid: int):
    """获取投顾组合识别结果"""
    db = get_portfolio_db()
    portfolio = db.get_portfolio(pid)
    if not portfolio:
        raise HTTPException(404, detail=f"组合 #{pid} 不存在")
    identified = db.get_identified(pid)
    return {"portfolio_id": pid, "portfolio_name": portfolio.get("name"), "count": len(identified), "data": identified}


@app.get("/api/portfolios/{pid}/history")
def get_portfolio_history(pid: int, days: int = Query(30, ge=1, le=365, description="最近N天")):
    """获取投顾组合收益走势"""
    db = get_portfolio_db()
    portfolio = db.get_portfolio(pid)
    if not portfolio:
        raise HTTPException(404, detail=f"组合 #{pid} 不存在")
    history = db.get_history(pid, days)
    return {"portfolio_id": pid, "portfolio_name": portfolio.get("name"), "count": len(history), "data": history}


@app.get("/api/portfolios/{pid}/export")
def export_portfolio(pid: int):
    """导出投顾组合完整数据（JSON）"""
    db = get_portfolio_db()
    portfolio = db.get_portfolio(pid)
    if not portfolio:
        raise HTTPException(404, detail=f"组合 #{pid} 不存在")
    return db.export_json(pid)


# ══════════════════════════════════════════════════════════════════════════════
#  System / Status
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "crawl_db_exists": CRAWL_DB.exists(), "portfolio_db_exists": PORTFOLIO_DB.exists()}


@app.get("/")
def root():
    """API 首页"""
    return {
        "name": "东方财富选手 & 大同证券投顾数据 API",
        "version": "1.0.0",
        "endpoints": {
            "东方财富选手数据": {
                "GET /api/players": "选手列表（支持排序、分页）",
                "GET /api/players/{zh_id}": "单个选手详情",
                "GET /api/players/{zh_id}/positions": "选手持仓",
                "GET /api/players/{zh_id}/trades": "选手调仓记录",
                "GET /api/players/top-performers": "当日盈利最高选手",
                "GET /api/positions/top-holdings": "持仓最多的股票排行",
                "GET /api/positions/distribution": "仓位分布统计",
                "GET /api/positions/all": "全部选手持仓",
                "GET /api/rankings/{rank_type}": "榜单排名数据（总榜/年榜/月榜/周榜/日榜）",
                "GET /api/follow": "关注列表",
                "POST /api/follow/{zh_id}": "关注选手",
                "DELETE /api/follow/{zh_id}": "取消关注",
                "GET /api/player-detail/{zh_id}": "选手实时详情（rtV2+持仓+调仓+排名）",
                "GET /api/search?q=": "搜索选手（按组合名或选手ID）",
                "GET /rankings": "公开实盘排行榜 HTML 页面",
                "GET /follow": "关注列表 HTML 页面",
                "GET /player/{zh_id}": "选手详情 HTML 页面",
            },
            "大同证券投顾数据": {
                "GET /api/portfolios": "投顾组合列表",
                "GET /api/portfolios/{pid}": "组合概况",
                "GET /api/portfolios/{pid}/positions": "组合持仓",
                "GET /api/portfolios/{pid}/trades": "组合调仓记录",
                "GET /api/portfolios/{pid}/identified": "组合识别结果",
                "GET /api/portfolios/{pid}/history": "组合收益走势",
                "GET /api/portfolios/{pid}/export": "导出组合完整数据",
            },
            "系统": {
                "GET /health": "健康检查",
                "GET /docs": "Swagger 文档",
            },
        },
    }