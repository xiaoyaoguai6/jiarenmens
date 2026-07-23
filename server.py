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
<title>东方财富 · 选手榜单排名</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f0f2f5; color: #1f2937; padding: 20px; }
  .container { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 22px; margin-bottom: 16px; color: #1e3a8a; }
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
  th, td { padding: 10px 14px; text-align: left; font-size: 14px; }
  th { background: #f8fafc; color: #475569; font-weight: 600;
       border-bottom: 2px solid #e2e8f0; }
  td { border-bottom: 1px solid #f1f5f9; }
  tr:hover td { background: #f8fafc; }
  .rank-num { font-weight: 600; color: #1e3a8a; width: 40px; }
  .positive { color: #dc2626; }
  .negative { color: #16a34a; }
  .zero { color: #9ca3af; }
  .fans { color: #6b7280; font-size: 13px; }
  .loading { text-align: center; padding: 40px; color: #6b7280; }
</style>
</head>
<body>
<div class="container">
  <h1>📊 东方财富选手榜单排名</h1>
  <div class="tabs" id="tabs"></div>
  <div class="info" id="info"></div>
  <div id="loading" class="loading">加载中...</div>
  <table id="table" style="display:none">
    <thead><tr><th>#</th><th>组合名</th><th>选手名</th><th>粉丝数</th><th>收益率</th></tr></thead>
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

// render tabs
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
  render();
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
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="rank-num">' + rank + '</td>'
      + '<td>' + esc(p.name) + '</td>'
      + '<td>' + esc(p.zh_id) + '</td>'
      + '<td class="fans">' + p.followers.toLocaleString() + '</td>'
      + '<td class="' + cls + '">' + sign + r.toFixed(2) + '%</td>';
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

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

loadData();
</script>
</body>
</html>"""


@app.get("/rankings", response_class=HTMLResponse)
def rankings_page():
    return _RANKINGS_HTML


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
                "GET /rankings": "榜单排名 HTML 页面",
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