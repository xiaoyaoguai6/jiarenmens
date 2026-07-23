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
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f0f2f5; color: #1f2937; padding: 20px; }
  .container { max-width: 900px; margin: 0 auto; }
  .nav { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
  .nav h1 { font-size: 22px; color: #1e3a8a; margin: 0; }
  .nav a { text-decoration: none; color: #1e3a8a; font-size: 14px; padding: 6px 14px;
           border: 1px solid #1e3a8a; border-radius: 6px; }
  .nav a:hover { background: #eff6ff; }
  .loading { text-align: center; padding: 40px; color: #6b7280; }
  .card { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card h2 { font-size: 16px; color: #1e3a8a; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
  .info-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr)); gap: 12px; }
  .info-item .label { font-size: 12px; color: #6b7280; }
  .info-item .value { font-size: 16px; font-weight: 600; }
  .positive { color: #dc2626; } .negative { color: #16a34a; } .zero { color: #9ca3af; }
  .rank-badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
                font-size: 12px; margin: 2px; background: #dbeafe; color: #1e3a8a; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #f1f5f9; }
  th { color: #475569; font-weight: 600; background: #f8fafc; }
  .error { text-align: center; padding: 40px; color: #dc2626; }
  .follow-btn { padding: 6px 16px; border-radius: 6px; border: 1px solid #1e3a8a;
                font-size: 14px; cursor: pointer; }
  .follow-btn:hover { background: #eff6ff; }
  .follow-btn.followed { background: #dbeafe; color: #1e3a8a; }
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <h1 id="playerName">选手详情</h1>
    <a href="/rankings">📊 排行榜</a>
    <a href="/follow">❤️ 关注列表</a>
  </div>
  <div id="loading" class="loading">加载中...</div>
  <div id="content" style="display:none"></div>
</div>
<script>
const zhId = location.pathname.split('/').pop();

async function load() {
  const loading = document.getElementById('loading');
  const content = document.getElementById('content');
  try {
    const r = await fetch('/api/player-detail/' + encodeURIComponent(zhId));
    if (!r.ok) { loading.textContent = '选手不存在或API错误'; return; }
    const d = await r.json();
    loading.style.display = 'none';
    content.style.display = '';

    const det = d.detail || {};
    document.getElementById('playerName').textContent = '👤 ' + (det.name || zhId);

    let html = '';

    // ── 基本信息 ──
    html += '<div class="card"><h2>📋 基本信息</h2><div class="info-grid">';
    const fields = [
      ['组合名称', det.name || '--'],
      ['选手ID', zhId],
      ['粉丝数', (det.followers||0).toLocaleString()],
      ['总收益率', fmtPct(det.total_return)],
      ['日收益率', fmtPct(det.daily_return)],
      ['净值', det.net_value != null ? Number(det.net_value).toFixed(4) : '--'],
      ['最大回撤', det.max_drawdown != null ? Number(det.max_drawdown).toFixed(2) + '%' : '--'],
      ['胜率', det.win_rate != null ? Number(det.win_rate).toFixed(2) + '%' : '--'],
      ['运行天数', det.days || '--'],
    ];
    fields.forEach(f => {
      html += '<div class="info-item"><div class="label">' + f[0] + '</div><div class="value">' + f[1] + '</div></div>';
    });
    if (det.intro) html += '<div class="info-item" style="grid-column:1/-1"><div class="label">简介</div><div class="value" style="font-size:14px;font-weight:400">' + esc(det.intro) + '</div></div>';
    if (det.labels && det.labels.length) {
      html += '<div class="info-item" style="grid-column:1/-1"><div class="label">标签</div><div class="value" style="font-size:13px;font-weight:400">' + det.labels.join(' · ') + '</div></div>';
    }
    html += '</div></div>';

    // ── 今日榜单排名 ──
    if (d.rankings && d.rankings.length) {
      html += '<div class="card"><h2>🏆 今日榜单排名</h2>';
      d.rankings.forEach(rk => {
        const sign = rk.return > 0 ? '+' : '';
        html += '<span class="rank-badge">' + esc(rk.rank_type) + ' 第 ' + rk.rank + ' 名 (' + sign + rk.return.toFixed(2) + '%)</span>';
      });
      html += '</div>';
    }

    // ── 持仓 ──
    html += '<div class="card"><h2>📦 持仓 (' + (d.positions||[]).length + ')</h2>';
    if (d.positions && d.positions.length) {
      html += '<table><thead><tr><th>股票</th><th>代码</th><th>成本价</th><th>现价</th><th>盈亏</th><th>仓位</th></tr></thead><tbody>';
      d.positions.forEach(p => {
        const pr = p.profit_ratio;
        const cls = pr > 0 ? 'positive' : pr < 0 ? 'negative' : 'zero';
        html += '<tr><td>' + esc(p.stock_name) + '</td><td>' + esc(p.stock_code) + '</td>'
          + '<td>' + (p.cost_price != null ? Number(p.cost_price).toFixed(2) : '--') + '</td>'
          + '<td>' + (p.current_price != null ? Number(p.current_price).toFixed(2) : '--') + '</td>'
          + '<td class="' + cls + '">' + (pr != null ? (pr > 0 ? '+' : '') + Number(pr).toFixed(2) + '%' : '--') + '</td>'
          + '<td>' + (p.position_ratio != null ? Number(p.position_ratio).toFixed(1) + '%' : '--') + '</td></tr>';
      });
      html += '</tbody></table>';
    } else { html += '<div style="color:#9ca3af;padding:8px 0">暂无持仓数据</div>'; }
    html += '</div>';

    // ── 调仓 ──
    html += '<div class="card"><h2>📋 调仓记录 (' + (d.trades||[]).length + ')</h2>';
    if (d.trades && d.trades.length) {
      html += '<table><thead><tr><th>股票</th><th>日期</th><th>买入</th><th>卖出</th></tr></thead><tbody>';
      d.trades.forEach(t => {
        html += '<tr><td>' + esc(t.stock_name) + '</td><td>' + esc(t.trade_date) + '</td>'
          + '<td>' + (t.buy_qty > 0 ? t.buy_qty : '--') + '</td>'
          + '<td>' + (t.sell_qty > 0 ? t.sell_qty : '--') + '</td></tr>';
      });
      html += '</tbody></table>';
    } else { html += '<div style="color:#9ca3af;padding:8px 0">暂无调仓记录</div>'; }
    html += '</div>';

    content.innerHTML = html;
  } catch(e) { loading.textContent = '加载失败: ' + e.message; }
}

function fmtPct(v) {
  if (v == null) return '--';
  const n = Number(v);
  const cls = n > 0 ? 'positive' : n < 0 ? 'negative' : 'zero';
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