"""
web_dashboard.py —— 东方财富看板
===================================
Flask 应用，包含：
  1. 公开实盘排行榜 + 关注 + 选手详情 + 实盘热股榜
  2. 大同证券投顾组合看板（保持不变）

启动:
    python scripts/web_dashboard.py --port 5000 --host 0.0.0.0
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, request, jsonify, Response

PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))
from src.storage.sqlite_storage import SQLiteStorage
from src.storage.portfolio_db import PortfolioDB
from src.utils.logger import setup_logger

logger = setup_logger()

DB_PATH = PROJ_ROOT / "data" / "crawl_data.db"
PORTFOLIO_DB_PATH = PROJ_ROOT / "data" / "portfolio.db"
EM_API = "https://emdcspzhapi.eastmoney.com/rtV2"
EM_HEADERS_FILE = PROJ_ROOT / "config" / "em_headers.json"

app = Flask(__name__)
storage = SQLiteStorage(DB_PATH)
_poll_lock = threading.Lock()

# ── Helpers ──

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=3)
    c.row_factory = sqlite3.Row
    return c

def _load_em_headers() -> dict:
    h = {"Accept-Encoding":"gzip","Content-Type":"application/json; charset=UTF-8",
         "EM-CHL":"taobao45","EM-CT":"","EM-OS":"Android","EM-PA":"1","EM-SL":"0","EM-UT":"",
         "User-Agent":"okhttp/3.12.13","Host":"emdcspzhapi.eastmoney.com"}
    if EM_HEADERS_FILE.exists():
        cfg = json.loads(EM_HEADERS_FILE.read_text(encoding="utf-8"))
        for k in ("EM-MD","EM-GT","EM-GV","EM-VER","EM-PKG"):
            if cfg.get(k): h[k] = cfg[k]
    return h

def _fetch_rtv2(zh_id: str) -> Optional[dict]:
    headers = _load_em_headers()
    body = {"args":{"reqUserid":"","zh":zh_id},"clientType":"cfzq","method":"combination_detail_97",
            "client":"android","appKey":"eastmoney","clientVersion":"10.13.5",
            "randomCode":str(uuid.uuid4()),"timestamp":int(time.time()*1000)}
    try:
        r = requests.post(EM_API, json=body, headers=headers, timeout=15)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != 0: return None
        return j["data"]
    except: return None

# ── Follow DB ──
_FOLLOW_DB_INITED = False
def _init_follow_db():
    global _FOLLOW_DB_INITED
    if _FOLLOW_DB_INITED: return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS followed_players (zh_id TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    _FOLLOW_DB_INITED = True

# ── Hot Stocks DB ──
_HOT_DB_INITED = False
def _init_hot_db():
    global _HOT_DB_INITED
    if _HOT_DB_INITED: return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS hot_stocks_cache (cache_type TEXT PRIMARY KEY, data TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    _HOT_DB_INITED = True

# ══════════════════════════════════════════════════════════════════════════════
#  API: 排行榜
# ══════════════════════════════════════════════════════════════════════════════

RANK_LABELS = {"总榜","年榜","月榜","周榜","日榜"}

@app.route("/api/rankings/<rank_type>")
def api_rankings(rank_type):
    if rank_type not in RANK_LABELS:
        return jsonify({"error":"invalid rank_type"}), 400
    players = storage.load_players()
    ranked = []
    for p in players:
        ranks = p.get("ranks",{})
        if isinstance(ranks, list): ranks = {}
        entry = ranks.get(rank_type)
        if entry and entry.get("return") is not None:
            ranked.append({"zh_id":p.get("zh_id"),"name":p.get("name",""),"followers":p.get("followers",0),"return":entry["return"]})
    ranked.sort(key=lambda x: x["return"] or 0, reverse=True)
    return jsonify({"rank_type":rank_type,"total":len(ranked),"data":ranked})

# ══════════════════════════════════════════════════════════════════════════════
#  API: 搜索
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip().lower()
    if not q: return jsonify({"total":0,"data":[]})
    players = storage.load_players()
    matched = []
    for p in players:
        name = (p.get("name") or "").lower()
        zh_id = (p.get("zh_id") or "").lower()
        if q in name or q in zh_id:
            matched.append({"zh_id":p.get("zh_id"),"name":p.get("name",""),"followers":p.get("followers",0),
                            "total_return":p.get("total_return",0),"daily_return":p.get("daily_return",0)})
    return jsonify({"total":len(matched),"data":matched[:50]})

# ══════════════════════════════════════════════════════════════════════════════
#  API: 关注
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/follow/<zh_id>", methods=["POST"])
def api_follow_add(zh_id):
    _init_follow_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO followed_players (zh_id) VALUES (?)", (zh_id,))
    return jsonify({"ok":True,"zh_id":zh_id})

@app.route("/api/follow/<zh_id>", methods=["DELETE"])
def api_follow_del(zh_id):
    _init_follow_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM followed_players WHERE zh_id=?", (zh_id,))
    return jsonify({"ok":True,"zh_id":zh_id})

@app.route("/api/follow")
def api_follow_list():
    _init_follow_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT zh_id,created_at FROM followed_players ORDER BY created_at DESC").fetchall()
        followed = [{"zh_id":r[0],"followed_at":r[1]} for r in rows]
    for f in followed:
        p = storage.load_player(f["zh_id"])
        if p and p.get("name"):
            f["name"] = p.get("name",""); f["followers"] = p.get("followers",0)
            f["total_return"] = p.get("total_return",0); f["daily_return"] = p.get("daily_return",0)
        else:
            try:
                rtv2 = _fetch_rtv2(f["zh_id"])
                if rtv2:
                    det = rtv2.get("detail",{})
                    f["name"] = det.get("zuheName") or det.get("uidNick") or ""
                    f["followers"] = int(det.get("concernCnt",0))
                    f["total_return"] = float(det.get("rate",0))
                    f["daily_return"] = float(det.get("rateDay",0))
            except: pass
    return jsonify({"total":len(followed),"data":followed})

@app.route("/api/follow/ids")
def api_follow_ids():
    _init_follow_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT zh_id FROM followed_players").fetchall()
    return jsonify({"ids":[r[0] for r in rows]})

# ══════════════════════════════════════════════════════════════════════════════
#  API: 选手详情
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/player-detail/<zh_id>")
def api_player_detail(zh_id):
    rtv2 = _fetch_rtv2(zh_id)
    if not rtv2:
        return jsonify({"error":"获取失败"}), 502
    detail = rtv2.get("detail",{})
    positions = rtv2.get("position",[])
    trades = rtv2.get("tradeSummary",[])
    # rankings from DB
    players = storage.load_players()
    rankings = []
    for rt in ("总榜","年榜","月榜","周榜","日榜"):
        ranked = []
        for p in players:
            rks = p.get("ranks",{})
            if isinstance(rks,list): rks = {}
            entry = rks.get(rt)
            if entry and entry.get("return") is not None:
                ranked.append((p.get("zh_id"),entry["return"]))
        ranked.sort(key=lambda x: x[1] or 0, reverse=True)
        for idx,(zid,val) in enumerate(ranked):
            if zid == zh_id:
                rankings.append({"rank_type":rt,"rank":idx+1,"return":val})
                break
    return jsonify({
        "zh_id":zh_id,
        "detail":{
            "name":detail.get("zuheName") or detail.get("uidNick") or "",
            "followers":int(detail.get("concernCnt",0)),
            "total_return":detail.get("rate"),"daily_return":detail.get("rateDay"),
            "return_5d":detail.get("rate5Day"),"return_20d":detail.get("rate20Day"),
            "return_60d":detail.get("rate60Day"),"return_250d":detail.get("rate250Day"),
            "net_value":detail.get("JZ"),"max_drawdown":detail.get("maxDrawDown"),
            "win_rate":detail.get("dealRate"),"days":detail.get("yxts"),
            "intro":detail.get("comment") or detail.get("uidComment") or "",
            "labels":[detail.get(k) for k in ("label1","label2","label3") if detail.get(k)],
        },
        "positions":[{"stock_name":p.get("__name",""),"stock_code":str(p.get("__code","")),
                       "cost_price":p.get("cbj"),"current_price":p.get("__zxjg"),
                       "profit_ratio":p.get("webYkRate"),"position_ratio":p.get("holdPos") or p.get("positionRateDetail")}
                      for p in (positions or [])],
        "trades":[{"stock_name":t.get("stkName",""),"trade_date":t.get("tzrq",""),
                    "buy_qty":t.get("lshj_mr",0),"sell_qty":t.get("lshj_mc",0)}
                   for t in (trades or [])],
        "rankings":rankings,
        "tendency":rtv2.get("tendency",[]),
        "tendency_summary":rtv2.get("tendencySummary",{}),
        "dimensions":rtv2.get("dimensions",{}),
        "evaluation":rtv2.get("evaluation",{}),
    })

# ══════════════════════════════════════════════════════════════════════════════
#  API: 实盘热股榜
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/hot-stocks")
def api_hot_stocks():
    _init_hot_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT cache_type,data,updated_at FROM hot_stocks_cache").fetchall()
    result = {}
    for r in rows:
        result[r[0]] = {"data":json.loads(r[1]) if r[1] else [],"updated_at":r[2]}
    return jsonify(result)

@app.route("/api/hot-stocks/refresh", methods=["POST"])
def api_hot_stocks_refresh():
    _init_hot_db()
    players = storage.load_players()
    def _get_ids(rank_types, n):
        ids = set()
        for rt in rank_types:
            ranked = []
            for p in players:
                rks = p.get("ranks",{})
                if isinstance(rks,list): rks = {}
                entry = rks.get(rt)
                if entry and entry.get("return") is not None:
                    ranked.append((p.get("zh_id"),entry["return"]))
            ranked.sort(key=lambda x: x[1] or 0, reverse=True)
            for z in ranked[:n]: ids.add(z[0])
        return ids
    hold_ids = _get_ids(("月榜","年榜"), 20)
    add_ids = _get_ids(("总榜","年榜","月榜","周榜"), 10)
    total = len(hold_ids) + len(add_ids)
    done = 0
    def _agg(zh_ids):
        nonlocal done
        result = {}
        for zh in zh_ids:
            rtv2 = _fetch_rtv2(zh)
            if rtv2:
                for pos in (rtv2.get("position") or []):
                    code = str(pos.get("__code",""))
                    if code:
                        if code in result: result[code]["score"] += 1
                        else: result[code] = {"stock_code":code,"stock_name":pos.get("__name",""),"score":1}
            done += 1
            if done < total: time.sleep(2)
        return result
    hold_data = _agg(hold_ids)
    add_data = _agg(add_ids)
    hold_sorted = sorted(hold_data.values(), key=lambda x: -x["score"])
    add_sorted = sorted(add_data.values(), key=lambda x: -x["score"])
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO hot_stocks_cache (cache_type,data,updated_at) VALUES (?,?,CURRENT_TIMESTAMP)",
                     ("holdings",json.dumps(hold_sorted,ensure_ascii=False)))
        conn.execute("INSERT OR REPLACE INTO hot_stocks_cache (cache_type,data,updated_at) VALUES (?,?,CURRENT_TIMESTAMP)",
                     ("add",json.dumps(add_sorted,ensure_ascii=False)))
    return jsonify({"ok":True,"holdings":{"count":len(hold_sorted),"players":len(hold_ids)},"add":{"count":len(add_sorted),"players":len(add_ids)}})

# ══════════════════════════════════════════════════════════════════════════════
#  HTML 页面
# ══════════════════════════════════════════════════════════════════════════════

# 从 server.py 移植的 HTML 模板
RANKINGS_HTML = open(Path(__file__).parent.parent / "data" / "_rankings.html", "r").read() if (Path(__file__).parent.parent / "data" / "_rankings.html").exists() else ""
FOLLOW_HTML = ""
PLAYER_HTML = ""
HOT_HTML = ""

# 直接内联 HTML（从 server.py 移植）
INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>东方财富看板</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f0f2f5; color: #1f2937; min-height: 100vh; }
  header { background: linear-gradient(135deg,#1e3a8a,#312e81); color: #fff;
           padding: 0 20px; display: flex; justify-content: space-between;
           align-items: center; height: 56px; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
  header .left { display: flex; align-items: center; gap: 20px; }
  header h1 { margin: 0; font-size: 17px; font-weight: 700; }
  .nav-tabs { display: flex; gap: 2px; background: rgba(255,255,255,0.1); border-radius: 8px; padding: 3px; }
  .nav-tab { padding: 5px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;
             color: rgba(255,255,255,0.7); transition: all 0.2s; font-weight: 500; user-select: none; }
  .nav-tab:hover { color: #fff; background: rgba(255,255,255,0.1); }
  .nav-tab.active { background: #fff; color: #1e3a8a; font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
  .view { display: none; padding: 16px; }
  .view.active { display: block; }
  .container { max-width: 960px; margin: 0 auto; }
  .search-box { display: flex; gap: 6px; margin-bottom: 14px; }
  .search-box input { flex:1; padding:8px 14px; border:1px solid #d1d5db; border-radius:6px; font-size:14px; outline:none; }
  .search-box input:focus { border-color:#1e3a8a; box-shadow:0 0 0 2px rgba(30,58,138,.1); }
  .search-box button { padding:8px 18px; border:none; border-radius:6px; background:#3b82f6; color:#fff; font-size:14px; cursor:pointer; }
  .search-box button:hover { background:#2563eb; }
  .tabs { display:flex; gap:6px; margin-bottom:14px; flex-wrap:wrap; }
  .tab { padding:8px 20px; border:1px solid #d1d5db; border-radius:6px; background:#fff; cursor:pointer; font-size:14px; color:#374151; }
  .tab:hover { background:#eff6ff; }
  .tab.active { background:#1e3a8a; color:#fff; border-color:#1e3a8a; }
  .info { font-size:13px; color:#6b7280; margin-bottom:10px; }
  .pagination { display:flex; justify-content:center; align-items:center; gap:10px; margin:16px 0; font-size:14px; }
  .pagination button { padding:6px 14px; border:1px solid #d1d5db; border-radius:4px; background:#fff; cursor:pointer; }
  .pagination button:disabled { opacity:.4; cursor:not-allowed; }
  .pagination button:hover:not(:disabled) { background:#eff6ff; }
  table { width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.08); }
  th, td { padding:9px 12px; text-align:left; font-size:14px; }
  th { background:#f8fafc; color:#475569; font-weight:600; border-bottom:2px solid #e2e8f0; }
  td { border-bottom:1px solid #f1f5f9; }
  tr:hover td { background:#f8fafc; }
  .rank-num { font-weight:600; color:#1e3a8a; width:36px; }
  .positive { color:#dc2626; } .negative { color:#16a34a; } .zero { color:#9ca3af; }
  .fans { color:#6b7280; font-size:13px; }
  .loading { text-align:center; padding:40px; color:#6b7280; }
  .player-link { color:#1e3a8a; text-decoration:none; font-weight:500; }
  .player-link:hover { text-decoration:underline; }
  .follow-btn { padding:3px 10px; border-radius:4px; border:1px solid #d1d5db; font-size:12px; cursor:pointer; background:#fff; color:#374151; }
  .follow-btn:hover { background:#eff6ff; }
  .follow-btn.followed { background:#dbeafe; color:#1e3a8a; border-color:#1e3a8a; }
  .search-results { display:none; }
  .sub-nav { display:flex; gap:8px; margin-bottom:14px; flex-wrap:wrap; }
  .sub-nav a { text-decoration:none; color:#1e3a8a; font-size:13px; padding:5px 12px; border:1px solid #1e3a8a; border-radius:6px; }
  .sub-nav a:hover { background:#eff6ff; }
  .sub-nav a.active { background:#1e3a8a; color:#fff; }
  .bar { display:flex; gap:10px; align-items:center; font-size:12px; color:rgba(255,255,255,0.8); }
  .bar button { background:rgba(255,255,255,0.15); color:#fff; border:1px solid rgba(255,255,255,0.2);
                padding:5px 12px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:500; }
  .bar button:hover { background:rgba(255,255,255,0.25); }
  .bar button:disabled { opacity:0.4; cursor:wait; }
  .add-box { display:flex; gap:8px; margin-bottom:14px; }
  .add-box input { flex:1; padding:8px 14px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; }
  .add-box input:focus { border-color:#1e3a8a; box-shadow:0 0 0 2px rgba(30,58,138,.1); }
  .add-box button { padding:8px 18px; border:none; border-radius:8px; background:#3b82f6; color:#fff; font-size:14px; cursor:pointer; white-space:nowrap; }
  .add-box button:hover { background:#2563eb; }
  .add-box button:disabled { opacity:.6; cursor:not-allowed; background:#93c5fd; }
  .add-msg { font-size:13px; margin-bottom:10px; padding:6px 12px; border-radius:6px; display:none; }
  .add-msg.success { display:block; background:#f0fdf4; color:#16a34a; border:1px solid #bbf7d0; }
  .add-msg.error { display:block; background:#fef2f2; color:#dc2626; border:1px solid #fecaca; }
  .refresh-bar { display:flex; gap:10px; align-items:center; margin-bottom:14px; flex-wrap:wrap; }
  .refresh-btn { padding:8px 20px; border:none; border-radius:8px; background:#3b82f6; color:#fff; font-size:14px; cursor:pointer; }
  .refresh-btn:hover { background:#2563eb; }
  .refresh-btn:disabled { opacity:.6; cursor:not-allowed; }
  .progress { font-size:13px; color:#d97706; margin-bottom:10px; display:none; padding:8px 14px;
              background:#fffbeb; border-radius:8px; border:1px solid #fde68a; }
  .score { font-weight:600; color:#dc2626; }
  .empty-state { text-align:center; padding:40px; color:#9ca3af; }
  /* 投顾组合原有样式 */
  #view-portfolios { padding: 16px; background: #f0f2f5; }
  .pf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 1400px; margin: 0 auto; }
  @media (max-width: 900px) { .pf-grid { grid-template-columns: 1fr; } }
  .pf-card { background: #fff; border-radius: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); overflow: hidden; }
  .pf-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
  .pf-head { padding: 18px 20px 14px; border-bottom: 1px solid #f3f4f6; display: flex; justify-content: space-between; align-items: flex-start; }
  .pf-head .info h2 { margin: 0; font-size: 16px; font-weight: 700; color: #111827; }
  .pf-head .info .advisor { color: #6b7280; font-size: 12px; margin-top: 2px; }
  .pf-head .meta { text-align: right; }
  .pf-head .meta .assets { font-size: 18px; font-weight: 700; color: #111827; }
  .pf-head .meta .return { font-size: 13px; font-weight: 600; margin-top: 2px; }
  .pf-stats { display: grid; grid-template-columns: repeat(3,1fr); border-bottom: 1px solid #f3f4f6; }
  .pf-stat { text-align: center; padding: 14px 10px; }
  .pf-stat + .pf-stat { border-left: 1px solid #f3f4f6; }
  .pf-stat .num { font-size: 20px; font-weight: 700; color: #1f2937; }
  .pf-stat .label { font-size: 11px; color: #9ca3af; }
  .pf-section { padding: 14px 20px 18px; }
  .pf-section h4 { margin: 0 0 10px; font-size: 13px; font-weight: 600; color: #374151; }
  .pf-section h4 .badge { display: inline-block; background: #eef2ff; color: #4f46e5; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; margin-left: 6px; }
  .pf-table { width: 100%; font-size: 12px; }
  .pf-table th { font-size: 10px; padding: 6px 8px; }
  .pf-table td { padding: 6px 8px; }
  .pf-table .code-mask { color: #9ca3af; font-family: monospace; font-size: 11px; }
  .pf-table .shares { text-align: right; }
  .pf-table .money { text-align: right; }
  .profit-badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
  .profit-badge.up { background: #fef2f2; color: #dc2626; }
  .profit-badge.down { background: #f0fdf4; color: #16a34a; }
  .profit-badge.flat { background: #f3f4f6; color: #6b7280; }
  .pf-card .loading { padding: 30px; text-align: center; color: #9ca3af; font-size: 13px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
  .pf-empty { padding: 40px 20px; text-align: center; color: #c0c4cc; font-size: 13px; }
  .pf-empty strong { color: #9ca3af; }
</style>
</head>
<body>
<header>
  <div class="left">
    <h1>📊 东方财富看板</h1>
    <div class="nav-tabs">
      <span class="nav-tab active" data-view="players" onclick="switchView('players')">实盘选手</span>
      <span class="nav-tab" data-view="portfolios" onclick="switchView('portfolios')">投顾组合</span>
    </div>
  </div>
  <div class="bar" id="header-bar-players">
    <span id="last-update">—</span>
  </div>
  <div class="bar" id="header-bar-portfolios" style="display:none">
    <span id="pf-last-update">—</span>
    <button id="pf-refresh-btn" onclick="refreshPortfolios()">↻ 刷新数据</button>
  </div>
</header>

<!-- ==================== 实盘选手 ==================== -->
<div id="view-players" class="view active">
<div class="container">
  <div class="sub-nav">
    <a href="javascript:showSubView('rankings')" id="sub-rankings" class="active">📊 排行榜</a>
    <a href="javascript:showSubView('follow')" id="sub-follow">❤️ 关注</a>
    <a href="javascript:showSubView('hot')" id="sub-hot">🔥 热股榜</a>
  </div>

  <!-- 排行榜 -->
  <div id="page-rankings">
    <div class="search-box">
      <input id="searchInput" placeholder="搜索选手名或组合ID..." onkeydown="if(event.key==='Enter') doSearch()">
      <button onclick="doSearch()">搜索</button>
    </div>
    <div class="tabs" id="rankTabs"></div>
    <div id="searchMode" class="search-results"></div>
    <div class="info" id="rankInfo"></div>
    <div id="rankLoading" class="loading">加载中...</div>
    <table id="rankTable" style="display:none">
      <thead><tr><th>#</th><th>组合名</th><th>选手名</th><th>粉丝数</th><th>收益率</th><th>操作</th></tr></thead>
      <tbody id="rankTbody"></tbody>
    </table>
    <div class="pagination" id="rankPagination" style="display:none">
      <button id="prevBtn" onclick="rankGoPage(-1)">上一页</button>
      <span id="pageInfo"></span>
      <button id="nextBtn" onclick="rankGoPage(1)">下一页</button>
    </div>
  </div>

  <!-- 关注 -->
  <div id="page-follow" style="display:none">
    <div class="add-box">
      <input id="addInput" placeholder="输入组合ID添加关注..." onkeydown="if(event.key==='Enter') addPlayer()">
      <button id="addBtn" onclick="addPlayer()">+ 添加</button>
    </div>
    <div class="add-msg" id="addMsg"></div>
    <div class="info" id="followInfo"></div>
    <div id="followLoading" class="loading">加载中...</div>
    <table id="followTable" style="display:none">
      <thead><tr><th>组合名</th><th>选手名</th><th>粉丝数</th><th>总收益</th><th>日收益</th><th>操作</th></tr></thead>
      <tbody id="followTbody"></tbody>
    </table>
    <div id="followEmpty" class="empty-state" style="display:none">还没有关注任何选手，去排行榜看看吧</div>
  </div>

  <!-- 热股榜 -->
  <div id="page-hot" style="display:none">
    <div class="tabs" id="hotTabs"></div>
    <div class="refresh-bar">
      <button class="refresh-btn" id="hotRefreshBtn" onclick="doHotRefresh()">🔄 刷新数据</button>
      <span class="info" id="hotUpdateInfo"></span>
    </div>
    <div class="progress" id="hotProgress"></div>
    <div id="hotLoading" class="loading">加载中...</div>
    <table id="hotTable" style="display:none">
      <thead><tr><th>#</th><th>股票名称</th><th>代码</th><th>关注人数</th></tr></thead>
      <tbody id="hotTbody"></tbody>
    </table>
    <div id="hotEmpty" class="empty-state" style="display:none">暂无数据，点击刷新数据获取</div>
  </div>
</div>
</div>

<!-- ==================== 投顾组合 ==================== -->
<div id="view-portfolios" class="view">
  <div class="pf-grid" id="pf-grid">
    <div class="pf-empty" style="grid-column:1/-1;"><strong>正在加载投顾组合数据...</strong></div>
  </div>
</div>

<script>
let followedSet = new Set();
let rankData = {};
let rankCurrentType = '总榜';
let rankCurrentPage = 0;
let hotCached = {};

// ═══ Tab switching ═══
function switchView(name) {
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.toggle("active", t.dataset.view === name));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
  document.getElementById("header-bar-players").style.display = name === "players" ? "flex" : "none";
  document.getElementById("header-bar-portfolios").style.display = name === "portfolios" ? "flex" : "none";
  if (name === "portfolios") loadPortfolios();
}

function showSubView(name) {
  document.querySelectorAll(".sub-nav a").forEach(a => a.classList.remove("active"));
  document.getElementById("sub-" + name).classList.add("active");
  document.getElementById("page-rankings").style.display = name === "rankings" ? "" : "none";
  document.getElementById("page-follow").style.display = name === "follow" ? "" : "none";
  document.getElementById("page-hot").style.display = name === "hot" ? "" : "none";
  if (name === "follow") loadFollow();
  if (name === "hot") loadHot();
}

// ═══ Rankings ═══
const RANK_TYPES = ['总榜','年榜','月榜','周榜','日榜'];
const PAGE_SIZE = 20;

const tabsEl = document.getElementById('rankTabs');
RANK_TYPES.forEach(t => {
  const btn = document.createElement('button');
  btn.className = 'tab' + (t === '总榜' ? ' active' : '');
  btn.textContent = t;
  btn.onclick = () => { rankCurrentType = t; rankCurrentPage = 0;
    document.querySelectorAll('#rankTabs .tab').forEach(b => b.classList.toggle('active', b.textContent === t));
    renderRank(); };
  tabsEl.appendChild(btn);
});

fetch('/api/follow/ids').then(r=>r.json()).then(d=>{ followedSet = new Set(d.ids); renderRank(); });

async function loadRank() {
  try {
    const res = await Promise.all(RANK_TYPES.map(t => fetch('/api/rankings/' + encodeURIComponent(t)).then(r => r.json())));
    RANK_TYPES.forEach((t,i) => { rankData[t] = res[i].data; });
    document.getElementById('rankLoading').style.display = 'none';
    document.getElementById('rankTable').style.display = '';
    document.getElementById('rankPagination').style.display = '';
    renderRank();
  } catch(e) { document.getElementById('rankLoading').textContent = '加载失败: ' + e.message; }
}

function renderRank() {
  const data = rankData[rankCurrentType] || [];
  const total = data.length;
  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
  if (rankCurrentPage >= totalPages) rankCurrentPage = totalPages - 1;
  const start = rankCurrentPage * PAGE_SIZE;
  const page = data.slice(start, start + PAGE_SIZE);
  document.getElementById('rankInfo').textContent = rankCurrentType + ' — 共 ' + total + ' 名选手';
  const tbody = document.getElementById('rankTbody');
  tbody.innerHTML = '';
  page.forEach((p, i) => {
    const rank = start + i + 1;
    const r = p.return;
    const cls = r > 0 ? 'positive' : r < 0 ? 'negative' : 'zero';
    const sign = r > 0 ? '+' : '';
    const isF = followedSet.has(p.zh_id);
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="rank-num">' + rank + '</td>'
      + '<td><a class="player-link" href="/player/' + encodeURIComponent(p.zh_id) + '" target="_blank">' + esc(p.name) + '</a></td>'
      + '<td class="fans">' + esc(p.zh_id) + '</td>'
      + '<td class="fans">' + (p.followers||0).toLocaleString() + '</td>'
      + '<td class="' + cls + '">' + sign + r.toFixed(2) + '%</td>'
      + '<td><button class="follow-btn' + (isF?' followed':'') + '" data-zh="' + p.zh_id + '" onclick="toggleFollow(this)">' + (isF?'已关注':'+ 关注') + '</button></td>';
    tbody.appendChild(tr);
  });
  document.getElementById('pageInfo').textContent = '第 ' + (rankCurrentPage+1) + '/' + totalPages + ' 页';
  document.getElementById('prevBtn').disabled = rankCurrentPage <= 0;
  document.getElementById('nextBtn').disabled = rankCurrentPage >= totalPages - 1;
}

function rankGoPage(delta) {
  const data = rankData[rankCurrentType] || [];
  const totalPages = Math.ceil(data.length / PAGE_SIZE) || 1;
  const np = rankCurrentPage + delta;
  if (np < 0 || np >= totalPages) return;
  rankCurrentPage = np;
  renderRank();
}

async function toggleFollow(btn) {
  const zh = btn.dataset.zh;
  const isF = followedSet.has(zh);
  try {
    if (isF) { await fetch('/api/follow/' + encodeURIComponent(zh), {method:'DELETE'}); followedSet.delete(zh); btn.textContent='+ 关注'; btn.classList.remove('followed'); }
    else { await fetch('/api/follow/' + encodeURIComponent(zh), {method:'POST'}); followedSet.add(zh); btn.textContent='已关注'; btn.classList.add('followed'); }
  } catch(e) { alert('操作失败'); }
}

// ═══ Search ═══
async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const sm = document.getElementById('searchMode');
  sm.style.display = 'block';
  document.getElementById('rankTable').style.display = 'none';
  document.getElementById('rankPagination').style.display = 'none';
  document.querySelectorAll('#rankTabs .tab').forEach(b => b.classList.remove('active'));
  document.getElementById('rankInfo').textContent = '搜索: ' + q;
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q));
    const d = await r.json();
    if (!d.total) { sm.innerHTML = '<div style="color:#6b7280;padding:20px;text-align:center">未找到匹配 "' + esc(q) + '" 的选手</div>'; return; }
    let html = '<div style="font-size:13px;color:#6b7280;margin-bottom:8px">找到 ' + d.total + ' 个结果</div>';
    html += '<table><thead><tr><th>组合名</th><th>选手名</th><th>粉丝数</th><th>总收益</th><th>日收益</th><th>操作</th></tr></thead><tbody>';
    d.data.forEach(p => {
      const isF = followedSet.has(p.zh_id);
      const rc = p.total_return > 0 ? 'positive' : p.total_return < 0 ? 'negative' : 'zero';
      const dc = p.daily_return > 0 ? 'positive' : p.daily_return < 0 ? 'negative' : 'zero';
      html += '<tr><td><a class="player-link" href="/player/' + encodeURIComponent(p.zh_id) + '" target="_blank">' + esc(p.name||'--') + '</a></td>'
        + '<td class="fans">' + esc(p.zh_id) + '</td>'
        + '<td>' + (p.followers||0).toLocaleString() + '</td>'
        + '<td class="' + rc + '">' + (p.total_return||0).toFixed(2) + '%</td>'
        + '<td class="' + dc + '">' + (p.daily_return||0).toFixed(2) + '%</td>'
        + '<td><button class="follow-btn' + (isF?' followed':'') + '" data-zh="' + p.zh_id + '" onclick="toggleFollow(this)">' + (isF?'已关注':'+ 关注') + '</button></td></tr>';
    });
    html += '</tbody></table>';
    sm.innerHTML = html;
  } catch(e) { sm.innerHTML = '<div style="color:#dc2626">搜索失败: ' + e.message + '</div>'; }
}

// ═══ Follow ═══
async function addPlayer() {
  const input = document.getElementById('addInput');
  const btn = document.getElementById('addBtn');
  const msg = document.getElementById('addMsg');
  const zh = input.value.trim();
  if (!zh) { msg.className='add-msg error'; msg.textContent='请输入组合ID'; msg.style.display='block'; return; }
  btn.disabled = true; btn.textContent = '添加中...';
  msg.className = 'add-msg'; msg.style.display = 'none';
  try {
    const r = await fetch('/api/follow/' + encodeURIComponent(zh), {method:'POST'});
    if (!r.ok) throw new Error('添加失败');
    msg.className='add-msg success'; msg.textContent='✅ 添加成功！'; msg.style.display='block';
    input.value = ''; btn.textContent='+ 添加'; btn.disabled=false;
    loadFollow();
  } catch(e) {
    msg.className='add-msg error'; msg.textContent='❌ ' + e.message; msg.style.display='block';
    btn.textContent='+ 添加'; btn.disabled=false;
  }
}

async function loadFollow() {
  const loading = document.getElementById('followLoading');
  const table = document.getElementById('followTable');
  const empty = document.getElementById('followEmpty');
  try {
    const r = await fetch('/api/follow'); const d = await r.json();
    loading.style.display = 'none';
    document.getElementById('followInfo').textContent = '共关注 ' + d.total + ' 名选手';
    if (!d.total) { empty.style.display = ''; table.style.display = 'none'; return; }
    table.style.display = ''; empty.style.display = 'none';
    const tbody = document.getElementById('followTbody'); tbody.innerHTML = '';
    d.data.forEach(p => {
      const dr = p.daily_return||0; const tr = p.total_return||0;
      const trCls = tr>0?'positive':tr<0?'negative':'zero';
      const drCls = dr>0?'positive':dr<0?'negative':'zero';
      const tr2 = document.createElement('tr');
      tr2.innerHTML = '<td><a class="player-link" href="/player/' + encodeURIComponent(p.zh_id) + '" target="_blank">' + esc(p.name||'--') + '</a></td>'
        + '<td class="fans">' + esc(p.zh_id) + '</td>'
        + '<td>' + (p.followers||0).toLocaleString() + '</td>'
        + '<td class="' + trCls + '">' + tr.toFixed(2) + '%</td>'
        + '<td class="' + drCls + '">' + dr.toFixed(2) + '%</td>'
        + '<td><button class="follow-btn" style="border-color:#dc2626;color:#dc2626" onclick="unfollow(\'' + p.zh_id + '\',this)">取消关注</button></td>';
      tbody.appendChild(tr2);
    });
  } catch(e) { loading.textContent = '加载失败: ' + e.message; }
}

async function unfollow(zh, btn) {
  try { await fetch('/api/follow/' + encodeURIComponent(zh), {method:'DELETE'}); loadFollow(); }
  catch(e) { alert('操作失败'); }
}

// ═══ Hot Stocks ═══
const HOT_TYPES = ['持仓榜','加仓榜'];
let hotCurrentType = '持仓榜';

const hotTabsEl = document.getElementById('hotTabs');
HOT_TYPES.forEach(t => {
  const btn = document.createElement('button');
  btn.className = 'tab' + (t === '持仓榜' ? ' active' : '');
  btn.textContent = t;
  btn.onclick = () => { hotCurrentType = t;
    document.querySelectorAll('#hotTabs .tab').forEach(b => b.classList.toggle('active', b.textContent === t));
    renderHot(); };
  hotTabsEl.appendChild(btn);
});

async function loadHot() {
  try {
    const r = await fetch('/api/hot-stocks'); hotCached = await r.json();
    document.getElementById('hotLoading').style.display = 'none';
    renderHot();
  } catch(e) { document.getElementById('hotLoading').textContent = '加载失败: ' + e.message; }
}

function renderHot() {
  const key = hotCurrentType === '持仓榜' ? 'holdings' : 'add';
  const entry = hotCached[key];
  const table = document.getElementById('hotTable');
  const empty = document.getElementById('hotEmpty');
  const info = document.getElementById('hotUpdateInfo');
  if (!entry || !entry.data || !entry.data.length) {
    table.style.display = 'none'; empty.style.display = ''; info.textContent = ''; return;
  }
  empty.style.display = 'none'; table.style.display = '';
  info.textContent = '上次更新: ' + (entry.updated_at || '--');
  const tbody = document.getElementById('hotTbody'); tbody.innerHTML = '';
  entry.data.forEach((s,i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="rank-num">' + (i+1) + '</td><td><strong>' + esc(s.stock_name) + '</strong></td><td>' + esc(s.stock_code) + '</td><td class="score">' + s.score + ' 人</td>';
    tbody.appendChild(tr);
  });
}

async function doHotRefresh() {
  const btn = document.getElementById('hotRefreshBtn');
  const progress = document.getElementById('hotProgress');
  btn.disabled = true; progress.style.display = 'block';
  progress.textContent = '⏳ 正在获取选手持仓数据，大约需要2-3分钟，请稍候...';
  try {
    const r = await fetch('/api/hot-stocks/refresh', {method:'POST'});
    const d = await r.json();
    progress.textContent = '✅ 刷新完成！持仓榜: ' + d.holdings.count + ' 只(' + d.holdings.players + '人) | 加仓榜: ' + d.add.count + ' 只(' + d.add.players + '人)';
    btn.disabled = false; loadHot();
  } catch(e) { progress.textContent = '❌ 刷新失败: ' + e.message; btn.disabled = false; }
}

// ═══ Portfolios ═══
async function refreshPortfolios() {
  const btn = document.getElementById('pf-refresh-btn');
  const info = document.getElementById('pf-last-update');
  btn.disabled = true; btn.textContent = '⏳ 刷新中...';
  info.textContent = '正在后台抓取数据，请稍候...';
  try {
    const r = await fetch('/api/portfolio/refresh-all', {method:'POST'});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error||'刷新失败');
    info.textContent = '刷新任务已启动，正在加载最新数据...';
    // 等待几秒后重新加载
    await new Promise(resolve => setTimeout(resolve, 3000));
    await loadPortfolios();
    info.textContent = '更新于 ' + new Date().toLocaleTimeString();
  } catch(e) {
    info.textContent = '刷新失败: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = '↻ 刷新数据';
  }
}

async function loadPortfolios() {
  const grid = document.getElementById('pf-grid');
  grid.innerHTML = '<div class="pf-empty" style="grid-column:1/-1;"><strong>加载中...</strong></div>';
  try {
    const res = await fetch('/api/portfolio/summary');
    const data = await res.json();
    const portfolios = data.portfolios || [];
    if (!portfolios.length) {
      grid.innerHTML = '<div class="pf-empty" style="grid-column:1/-1;"><strong>暂无投顾组合数据</strong></div>';
      return;
    }
    grid.innerHTML = '';
    for (const p of portfolios) {
      const card = document.createElement('div'); card.className = 'pf-card';
      card.innerHTML = buildPfCard(p);
      grid.appendChild(card);
      loadPfDetail(p.id, card);
    }
  } catch(e) { grid.innerHTML = '<div class="pf-empty" style="grid-column:1/-1;"><strong>加载失败: ' + e.message + '</strong></div>'; }
}

function buildPfCard(p) {
  const tr = (p.total_return||0); const rc = tr>=0?'pos-up':'pos-down'; const rs = (tr*100).toFixed(2)+'%';
  const assets = (p.total_assets||0).toLocaleString('zh-CN',{minimumFractionDigits:2});
  return '<div class="pf-head"><div class="info"><h2>#' + p.id + ' ' + esc(p.name||'—') + '</h2><div class="advisor">👤 ' + esc(p.advisor||'—') + '</div></div><div class="meta"><div class="assets">¥' + assets + '</div><div class="assets-label">总资产</div><div class="return ' + rc + '">总收益 ' + rs + '</div></div></div><div class="pf-stats"><div class="pf-stat"><div class="num" id="pf-pos-' + p.id + '">—</div><div class="label">持仓</div></div><div class="pf-stat"><div class="num" id="pf-trd-' + p.id + '">—</div><div class="label">调仓</div></div><div class="pf-stat"><div class="num" id="pf-idf-' + p.id + '">—</div><div class="label">已识别</div></div></div><div id="pf-det-' + p.id + '"><div class="loading">加载明细</div></div>';
}

async function loadPfDetail(pid, cardEl) {
  try {
    const res = await fetch('/api/portfolio/' + pid); const data = await res.json();
    if (!data.portfolio) { document.getElementById('pf-det-'+pid).innerHTML = '<div class="pf-empty">无数据</div>'; return; }
    document.getElementById('pf-pos-'+pid).textContent = (data.positions||[]).length;
    document.getElementById('pf-trd-'+pid).textContent = (data.trades||[]).length;
    document.getElementById('pf-idf-'+pid).textContent = (data.identified||[]).length;
    let html = '<div class="pf-section"><h4>持仓明细 <span class="badge">' + (data.positions||[]).length + ' 只</span></h4>';
    if (data.positions && data.positions.length) {
      html += '<table class="pf-table"><thead><tr><th>代码</th><th>名称</th><th>数量</th><th>现价</th><th>成本价</th><th>市值</th><th>盈亏</th><th>盈亏比</th><th>仓位%</th></tr></thead><tbody>';
      for (const pos of data.positions) {
        const profit = pos.profit||0; const pc = profit>=0?'up':'down'; const ps = profit>=0?'+'+profit.toFixed(2):profit.toFixed(2);
        const pr = pos.profit_ratio||ps; const por = pos.position_ratio||0;
        const curPx = (pos.current_value||0) / (pos.shares||1);
        const code = pos.stock_code||''; const name = pos.stock_name||'';
        const isMasked = code.includes('***');
        let dCode = code, dName = name;
        if (isMasked && pos.identified_code) { dCode = '<span style="color:#16a34a">' + esc(pos.identified_code) + '</span>'; dName = '<span style="color:#16a34a">' + esc(pos.identified_name) + '</span>'; }
        else if (isMasked) { dCode = code.replace(/\*/g,'<span style="color:#d1d5db;">*</span>'); dName = '<span style="color:#d1d5db;">' + esc(name) + '</span>'; }
        else { dCode = esc(code); dName = esc(name); }
        html += '<tr><td class="code-mask">' + dCode + '</td><td>' + dName + '</td><td class="shares">' + (pos.shares||0) + '</td><td class="money">' + curPx.toFixed(2) + '</td><td class="money">' + (pos.cost_price||0).toFixed(2) + '</td><td class="money">' + (pos.current_value||0).toFixed(2) + '</td><td class="money ' + pc + '">' + ps + '</td><td><span class="profit-badge ' + pc + '">' + pr + '</span></td><td class="shares">' + por.toFixed(1) + '</td></tr>';
      }
      html += '</tbody></table>';
    } else { html += '<div class="pf-empty">暂无持仓数据</div>'; }
    html += '</div>';
    if (data.trades && data.trades.length) {
      html += '<div class="pf-section" style="padding-top:0;"><h4>最近调仓 <span class="badge">' + data.trades.length + ' 条</span></h4><table class="pf-table"><thead><tr><th>方向</th><th>时间</th><th>代码</th><th>名称</th><th>价格</th><th>数量</th><th>金额</th></tr></thead><tbody>';
      for (const t of data.trades) {
        const isBuy = (t.direction||'').includes('买');
        const tag = isBuy ? '<span class="profit-badge up">买入</span>' : '<span class="profit-badge down">卖出</span>';
        const tc = t.stock_code||''; const tn = t.stock_name||'';
        html += '<tr><td>' + tag + '</td><td style="color:#9ca3af;font-size:11px;">' + (t.trade_time||'').slice(0,16) + '</td><td class="code-mask">' + esc(tc) + '</td><td>' + esc(tn) + '</td><td class="money">' + (t.price||0).toFixed(2) + '</td><td class="shares">' + (t.quantity||0) + '</td><td class="money">' + (t.amount||0).toFixed(0) + '</td></tr>';
      }
      html += '</tbody></table></div>';
    }
    if (data.chart && data.chart.length > 5) {
      html += '<div class="pf-section" style="padding-top:0;"><h4>收益走势</h4>' + buildMiniChart(data.chart) + '</div>';
    }
    document.getElementById('pf-det-'+pid).innerHTML = html;
  } catch(e) { document.getElementById('pf-det-'+pid).innerHTML = '<div class="pf-empty">加载失败</div>'; }
}

function buildMiniChart(data) {
  if (!data || data.length < 2) return '<div style="color:#9ca3af;text-align:center;padding:20px;">数据不足</div>';
  const w=600,h=160,pad={t:16,r:16,b:24,l:50},cw=w-pad.l-pad.r,ch=h-pad.t-pad.b;
  const points = data.slice().reverse();
  const assets = points.map(p=>p.asset_value||0);
  const hs300 = points.map(p=>p.hs300_value||0);
  const baseA = assets[0]||1, baseH = hs300[0]||1;
  const aPct = assets.map(v=>(v-baseA)/baseA*100);
  const hPct = hs300.map(v=>(v-baseH)/baseH*100);
  const all = aPct.concat(hPct);
  const minV = Math.min.apply(null,all), maxV = Math.max.apply(null,all);
  const range = maxV-minV||1, padR = range*0.12;
  const ym = minV-padR, yM = maxV+padR;
  const x = i => pad.l + (i/(points.length-1))*cw;
  const y = v => pad.t + ch - ((v-ym)/(yM-ym))*ch;
  const line = vals => vals.map((v,i)=>(i===0?'M':'L')+x(i).toFixed(1)+','+y(v).toFixed(1)).join('');
  function fmtDate(d) { const s=d||''; return s.length>=8?s.slice(2,4)+'/'+s.slice(4,6):s; }
  let html = '<svg width="100%" height="'+h+'" viewBox="0 0 '+w+' '+h+'" style="font-size:10px;overflow:visible;">';
  for (let gi=0;gi<=4;gi++) { const gy=ym+(yM-ym)*(gi/4),gyPx=y(gy); html += '<line x1="'+pad.l+'" y1="'+gyPx+'" x2="'+(w-pad.r)+'" y2="'+gyPx+'" stroke="#f0f0f0" stroke-width="1"/><text x="'+(pad.l-4)+'" y="'+(gyPx+3)+'" text-anchor="end" fill="#9ca3af">'+gy.toFixed(1)+'%</text>'; }
  [0,Math.floor(points.length/2),points.length-1].forEach(i=>{ html += '<text x="'+x(i)+'" y="'+(h-4)+'" text-anchor="middle" fill="#9ca3af">'+fmtDate(points[i].record_date)+'</text>'; });
  html += '<path d="'+line(hPct)+'" fill="none" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4,3"/>';
  html += '<path d="'+line(aPct)+'" fill="none" stroke="#4f46e5" stroke-width="2"/>';
  const la = aPct[aPct.length-1], lh = hPct[hPct.length-1];
  html += '<rect x="'+(w-140)+'" y="4" width="136" height="38" rx="4" fill="white" stroke="#e5e7eb" stroke-width="1"/>';
  html += '<circle cx="'+(w-130)+'" cy="14" r="4" fill="#4f46e5"/><text x="'+(w-120)+'" y="18" fill="#374151">组合收益 <tspan fill="'+(la>=0?'#dc2626':'#16a34a')+'">'+(la>=0?'+':'')+la.toFixed(2)+'%</tspan></text>';
  html += '<circle cx="'+(w-130)+'" cy="30" r="4" fill="#d1d5db"/><text x="'+(w-120)+'" y="34" fill="#9ca3af">沪深300 <tspan>'+(lh>=0?'+':'')+lh.toFixed(2)+'%</tspan></text>';
  html += '</svg>'; return html;
}

function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

// Boot
loadRank();
</script>
</body>
</html>"""


PLAYER_PAGE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>选手详情</title>
<style>
  :root{--primary:#1e3a8a;--bg:#f0f4f9;--card:#fff;--text:#1e293b;--text2:#64748b;--border:#e2e8f0;--success:#16a34a;--danger:#dc2626;--radius:12px;--shadow:0 1px 4px rgba(0,0,0,.06)}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);padding:24px}
  .container{max-width:1000px;margin:0 auto}
  .nav{display:flex;align-items:center;gap:12px;margin-bottom:24px;flex-wrap:wrap}
  .nav-back{text-decoration:none;color:var(--text2);font-size:14px;padding:6px 14px;border:1px solid var(--border);border-radius:8px}
  .nav-back:hover{background:#eff6ff;color:var(--primary)}
  .nav-title{font-size:20px;font-weight:700;color:var(--text);flex:1}
  .nav-links{display:flex;gap:8px}
  .nav-links a{text-decoration:none;color:var(--text2);font-size:13px;padding:6px 12px;border:1px solid var(--border);border-radius:8px}
  .nav-links a:hover{background:#eff6ff;color:var(--primary)}
  .loading,.error{text-align:center;padding:60px 20px;color:var(--text2);font-size:15px}
  .error{color:var(--danger)}
  .card{background:var(--card);border-radius:var(--radius);padding:20px 24px;margin-bottom:16px;box-shadow:var(--shadow)}
  .card-title{font-size:13px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:16px;display:flex;align-items:center;gap:6px}
  .metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px}
  .metric{padding:14px;border-radius:10px;background:#f8fafc;text-align:center}
  .metric .label{font-size:11px;color:var(--text2);margin-bottom:4px}
  .metric .value{font-size:18px;font-weight:700}
  .c-positive{color:var(--danger)}.c-negative{color:var(--success)}.c-zero{color:var(--text2)}.c-primary{color:var(--primary)}
  .rankings-wrap{display:flex;gap:8px;flex-wrap:wrap}
  .rank-badge{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#eff6ff;color:var(--primary);border:1px solid rgba(30,58,138,.15)}
  .chart-wrap{position:relative;width:100%;height:260px}
  .chart-wrap canvas{width:100%;height:100%;border-radius:8px}
  .chart-legend{display:flex;gap:20px;justify-content:center;margin-top:10px;font-size:12px}
  .chart-legend .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #f1f5f9;white-space:nowrap}
  th{color:var(--text2);font-weight:600;font-size:11px;background:#f8fafc}
  .table-wrap{overflow-x:auto}
  .scores{display:flex;flex-wrap:wrap;gap:20px;align-items:center}
  @media(max-width:640px){body{padding:12px}.metrics{grid-template-columns:repeat(3,1fr)}}
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a class="nav-back" href="javascript:history.back()">← 返回</a>
    <span class="nav-title" id="playerName">选手详情</span>
  </div>
  <div id="loading" class="loading"><div style="font-size:24px;margin-bottom:8px">⏳</div>加载中...</div>
  <div id="content" style="display:none"></div>
</div>
<script>
const zhId = location.pathname.split('/').pop();
async function load() {
  const loading=document.getElementById('loading'),content=document.getElementById('content');
  try {
    const r=await fetch('/api/player-detail/'+encodeURIComponent(zhId));
    if(!r.ok){loading.className='error';loading.textContent='❌ API错误';return;}
    const d=await r.json();loading.style.display='none';content.style.display='';
    const det=d.detail||{};document.getElementById('playerName').textContent='👤 '+(det.name||zhId);
    let html='';
    html+='<div class="card"><div class="card-title">📊 关键指标</div><div class="metrics">';
    const ms=[['总收益率',fmtPct(det.total_return)],['日收益率',fmtPct(det.daily_return)],['净值',det.net_value!=null?Number(det.net_value).toFixed(4):'--'],['最大回撤',det.max_drawdown!=null?Number(det.max_drawdown).toFixed(2)+'%':'--'],['日胜率',det.win_rate!=null?Number(det.win_rate).toFixed(1)+'%':'--'],['运行天数',det.days?Number(det.days).toLocaleString():'--'],['粉丝数',det.followers?Number(det.followers).toLocaleString():'0'],['5日收益',fmtPct(det.return_5d)],['20日收益',fmtPct(det.return_20d)],['60日收益',fmtPct(det.return_60d)],['250日收益',fmtPct(det.return_250d)]];
    ms.forEach(m=>{html+='<div class="metric"><div class="label">'+m[0]+'</div><div class="value">'+m[1]+'</div></div>';});
    html+='</div></div>';
    // Radar chart
    const ev=d.evaluation||{};const dim=d.dimensions||{};
    const si=[{label:'收益能力',key:'profitRateScore'},{label:'日胜率',key:'dayWinRateScore'},{label:'风控水平',key:'maxDrawdownScore'},{label:'夏普比',key:'sharpeRatioScore'},{label:'分散度',key:'investmentDispersionScore'},{label:'综合评分',key:'score'}];
    const hasScores=si.some(s=>ev[s.key]!=null);
    if(hasScores){
      html+='<div class="card"><div class="card-title">🎯 分析评分（六维图）</div><div class="scores">';
      html+='<div style="flex:1;min-width:280px;max-width:400px"><canvas id="radarChart" style="width:100%;height:280px"></canvas></div>';
      html+='<div style="flex:0 0 auto;font-size:13px;color:var(--text2)">';
      si.forEach(s=>{const v=ev[s.key]!=null?Math.round(Number(ev[s.key])):null;html+='<div style="display:flex;align-items:center;gap:8px;padding:3px 0"><span style="width:10px;height:10px;border-radius:2px;background:var(--primary)"></span><span>'+s.label+'</span><span style="font-weight:600;color:var(--text)">'+(v!=null?v+'分':'--')+'</span></div>';});
      html+='</div></div></div>';
    }
    // Trend chart
    const tendency=d.tendency||[];
    if(tendency.length>1){
      html+='<div class="card"><div class="card-title">📈 收益率走势</div><div class="chart-wrap"><canvas id="trendChart"></canvas></div><div class="chart-legend"><span><span class="dot" style="background:var(--primary)"></span> 组合收益率</span><span><span class="dot" style="background:#f59e0b"></span> 基准指数</span></div></div>';
    }
    // Rankings
    if(d.rankings&&d.rankings.length){
      html+='<div class="card"><div class="card-title">🏆 今日榜单排名</div><div class="rankings-wrap">';
      d.rankings.forEach(rk=>{const s=rk.return>0?'+':'';html+='<span class="rank-badge">'+esc(rk.rank_type)+' 第 '+rk.rank+' 名 ('+s+rk.return.toFixed(2)+'%)</span>';});
      html+='</div></div>';
    }
    // Tendency summary
    const ts=d.tendency_summary||{};
    if(ts.beatIndex!=null){html+='<div class="card"><div class="card-title">📊 跑赢指数</div><div class="metrics" style="grid-template-columns:repeat(3,1fr)"><div class="metric"><div class="label">累计收益</div><div class="value">'+fmtPct(ts.profit)+'</div></div><div class="metric"><div class="label">跑赢指数</div><div class="value c-primary">'+(ts.beatIndex!=null?ts.beatIndex+'%':'--')+'</div></div><div class="metric"><div class="label">跑赢概率</div><div class="value c-primary">'+(ts.beatRate!=null?ts.beatRate+'%':'--')+'</div></div></div></div>';}
    // Positions
    const positions=d.positions||[];
    html+='<div class="card"><div class="card-title">📦 持仓 ('+positions.length+')</div>';
    if(positions.length){html+='<div class="table-wrap"><table><thead><tr><th>股票</th><th>代码</th><th>成本价</th><th>现价</th><th>盈亏</th><th>仓位</th></tr></thead><tbody>';
      positions.forEach(p=>{const pr=p.profit_ratio;const cls=pr>0?'c-positive':pr<0?'c-negative':'c-zero';html+='<tr><td><strong>'+esc(p.stock_name)+'</strong></td><td>'+esc(p.stock_code)+'</td><td>'+(p.cost_price!=null?Number(p.cost_price).toFixed(2):'--')+'</td><td>'+(p.current_price!=null?Number(p.current_price).toFixed(2):'--')+'</td><td class="'+cls+'">'+(pr!=null?(pr>0?'+':'')+Number(pr).toFixed(2)+'%':'--')+'</td><td>'+(p.position_ratio!=null?Number(p.position_ratio).toFixed(1)+'%':'--')+'</td></tr>';});
      html+='</tbody></table></div>';}else{html+='<div style="color:var(--text2);padding:8px 0">暂无持仓数据</div>';}
    html+='</div>';
    // Trades
    const trades=d.trades||[];
    html+='<div class="card"><div class="card-title">📋 调仓记录 ('+trades.length+')</div>';
    if(trades.length){html+='<div class="table-wrap"><table><thead><tr><th>股票</th><th>日期</th><th>方向</th></tr></thead><tbody>';
      trades.forEach(t=>{const dir=t.buy_qty>0?'买入':t.sell_qty>0?'卖出':'--';const dirCls=t.buy_qty>0?'c-positive':t.sell_qty>0?'c-negative':'';const qty=t.buy_qty>0?t.buy_qty:t.sell_qty;html+='<tr><td><strong>'+esc(t.stock_name)+'</strong></td><td>'+esc(t.trade_date)+'</td><td class="'+dirCls+'">'+dir+' '+qty+'</td></tr>';});
      html+='</tbody></table></div>';}else{html+='<div style="color:var(--text2);padding:8px 0">暂无调仓记录</div>';}
    html+='</div>';
    content.innerHTML=html;
    if(tendency.length>1)drawChart(tendency);
    if(hasScores)setTimeout(()=>drawRadar(ev),50);
  }catch(e){loading.className='error';loading.textContent='❌ 加载失败: '+e.message;}
}

function drawChart(data){
  const canvas=document.getElementById('trendChart');const rect=canvas.parentElement.getBoundingClientRect();
  const dpr=window.devicePixelRatio||1;const W=rect.width||900,H=260;
  canvas.width=W*dpr;canvas.height=H*dpr;canvas.style.width=W+'px';canvas.style.height=H+'px';
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
  const pad={top:20,right:20,bottom:30,left:50},cw=W-pad.left-pad.right,ch=H-pad.top-pad.bottom;
  let points=data.map(d=>({date:d.yk_date||'',total:parseFloat(d.totalRate)||0,index:parseFloat(d.indexRate)||0}));
  points.sort((a,b)=>a.date.localeCompare(b.date));
  const allVals=points.flatMap(p=>[p.total,p.index]);
  const dataMin=Math.min(...allVals,0),dataMax=Math.max(...allVals);
  const yMin=Math.min(0,dataMin),yMax=dataMax<=0?10:Math.max(dataMax,dataMax*1.05);
  const yRange=yMax-yMin||1,xStep=cw/(points.length-1||1);
  function xPos(i){return pad.left+i*xStep}
  function yPos(v){return pad.top+ch-((v-yMin)/yRange)*ch}
  ctx.strokeStyle='#e2e8f0';ctx.lineWidth=1;
  for(let i=0;i<=5;i++){const y=pad.top+(ch/5)*i;ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(W-pad.right,y);ctx.stroke();const val=yMax-(yRange/5)*i;ctx.fillStyle='#94a3b8';ctx.font='11px sans-serif';ctx.textAlign='right';ctx.fillText(val.toFixed(1)+'%',pad.left-6,y+4);}
  if(yMin<0&&yMax>0){const y0=yPos(0);ctx.strokeStyle='#cbd5e1';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(pad.left,y0);ctx.lineTo(W-pad.right,y0);ctx.stroke();ctx.setLineDash([]);}
  ctx.strokeStyle='#1e3a8a';ctx.lineWidth=2;ctx.beginPath();points.forEach((p,i)=>{i===0?ctx.moveTo(xPos(i),yPos(p.total)):ctx.lineTo(xPos(i),yPos(p.total));});ctx.stroke();
  ctx.strokeStyle='#f59e0b';ctx.lineWidth=1.5;ctx.setLineDash([4,4]);ctx.beginPath();points.forEach((p,i)=>{i===0?ctx.moveTo(xPos(i),yPos(p.index)):ctx.lineTo(xPos(i),yPos(p.index));});ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle='#94a3b8';ctx.font='10px sans-serif';ctx.textAlign='center';
  [0,Math.floor(points.length/2),points.length-1].forEach(i=>{const ds=points[i].date||'';ctx.fillText(ds.length>=8?ds.slice(2):ds,xPos(i),H-pad.bottom+16);});
}

function drawRadar(ev){
  const canvas=document.getElementById('radarChart');if(!canvas)return;
  const rect=canvas.parentElement.getBoundingClientRect();const dpr=window.devicePixelRatio||1;
  const w=rect.width||320,h=280;canvas.width=w*dpr;canvas.height=h*dpr;canvas.style.width=w+'px';canvas.style.height=h+'px';
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
  const labels=['收益能力','日胜率','风控水平','夏普比','分散度','综合评分'];
  const keys=['profitRateScore','dayWinRateScore','maxDrawdownScore','sharpeRatioScore','investmentDispersionScore','score'];
  const values=keys.map(k=>ev[k]!=null?Math.min(Number(ev[k]),100)/100:0);
  const cx=w*0.42,cy=h*0.5,r=Math.min(cx,cy)*0.7,levels=5,angleStep=(Math.PI*2)/labels.length,rot=-Math.PI/2;
  function pt(i,radius){return{x:cx+radius*Math.cos(rot+angleStep*i),y:cy+radius*Math.sin(rot+angleStep*i)}}
  for(let lv=1;lv<=levels;lv++){const radius=(r/levels)*lv;ctx.beginPath();for(let i=0;i<=labels.length;i++){const p=pt(i%labels.length,radius);i===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y);}ctx.closePath();ctx.strokeStyle='#e2e8f0';ctx.lineWidth=1;ctx.stroke();}
  for(let i=0;i<labels.length;i++){const p=pt(i,r);ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(p.x,p.y);ctx.strokeStyle='#e2e8f0';ctx.lineWidth=1;ctx.stroke();const lp=pt(i,r+22);ctx.fillStyle='#475569';ctx.font='11px -apple-system,"PingFang SC",sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(labels[i],lp.x,lp.y);}
  ctx.beginPath();for(let i=0;i<=labels.length;i++){const idx=i%labels.length,radius=r*values[idx],p=pt(idx,radius);i===0?ctx.moveTo(p.x,p.y):ctx.lineTo(p.x,p.y);}ctx.closePath();ctx.fillStyle='rgba(30,58,138,0.15)';ctx.fill();ctx.strokeStyle='#1e3a8a';ctx.lineWidth=2;ctx.stroke();
  for(let i=0;i<labels.length;i++){const radius=r*values[i],p=pt(i,radius);ctx.beginPath();ctx.arc(p.x,p.y,4,0,Math.PI*2);ctx.fillStyle='#1e3a8a';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke();}
}

function fmtPct(v){if(v==null)return'--';const n=Number(v);const cls=n>0?'c-positive':n<0?'c-negative':'c-zero';const sign=n>0?'+':'';return'<span class="'+cls+'">'+sign+n.toFixed(2)+'%</span>';}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
load();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html; charset=utf-8")

@app.route("/player/<zh_id>")
def player_page(zh_id):
    return Response(PLAYER_PAGE_HTML, mimetype="text/html; charset=utf-8")

# ══════════════════════════════════════════════════════════════════════════════
#  原有 API（兼容）
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/players")
def api_players():
    with _conn() as c:
        rows = c.execute("SELECT p.zh_id, p.name, p.updated_at FROM players p ORDER BY p.updated_at DESC").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/positions")
def api_positions():
    zh = (request.args.get("zh") or "").strip()
    if not zh: return jsonify([])
    with _conn() as c:
        r = c.execute("SELECT MAX(crawl_date) d FROM positions WHERE zh_id=?", (zh,)).fetchone()
        if not r or not r["d"]: return jsonify([])
        d = r["d"]
        rows = c.execute("SELECT stock_code,stock_name,cost_price,current_price,profit_ratio,position_ratio,crawl_date FROM positions WHERE zh_id=? AND crawl_date=? ORDER BY position_ratio DESC", (zh,d)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/trades")
def api_trades():
    zh = (request.args.get("zh") or "").strip()
    if not zh: return jsonify([])
    with _conn() as c:
        r = c.execute("SELECT MAX(crawl_date) d FROM trades WHERE zh_id=?", (zh,)).fetchone()
        if not r or not r["d"]: return jsonify([])
        d = r["d"]
        rows = c.execute("SELECT stock_code,stock_name,direction,trade_date,position_change,position_value,position_ratio,crawl_date FROM trades WHERE zh_id=? AND crawl_date=? ORDER BY trade_date DESC", (zh,d)).fetchall()
        return jsonify([dict(r) for r in rows])

# ══════════════════════════════════════════════════════════════════════════════
#  投顾组合 API（保持不变）
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/portfolio/summary")
def api_portfolio_summary():
    db = PortfolioDB(PORTFOLIO_DB_PATH)
    return jsonify({"summary": db.summary(), "portfolios": [db.get_portfolio(pid) for pid in [278, 413] if db.get_portfolio(pid)]})

@app.route("/api/portfolio/<int:pid>")
def api_portfolio_detail(pid):
    db = PortfolioDB(PORTFOLIO_DB_PATH)
    portfolio = db.get_portfolio(pid)
    if not portfolio: return jsonify({"portfolio":None,"positions":[],"trades":[],"identified":[]})
    total_assets = portfolio.get("total_assets") or 0
    positions = db.get_positions(pid)
    identified = db.get_identified(pid)
    for pos in positions:
        val = pos.get("current_value") or 0; shares = pos.get("shares",0) or 0
        pos["position_ratio"] = round(val/total_assets*100,2) if total_assets>0 else 0
        pos["current_price_calc"] = round(val/shares,4) if shares>0 else 0
        prefix = (pos.get("stock_code") or "")[:3]
        unit_price = val/shares if shares>0 else 0
        candidates = [i for i in identified if (i.get("stock_code") or "").startswith(prefix)]
        if candidates:
            candidates.sort(key=lambda idf: (abs((idf.get("match_price") or idf.get("current_price") or 0) - unit_price)/unit_price if unit_price>0 and (idf.get("match_price") or idf.get("current_price") or 0)>0 else 999, -(idf.get("score") or 0)))
            best = candidates[0]
            pos["identified_code"] = best.get("stock_code"); pos["identified_name"] = best.get("stock_name")
            pos["identified_confidence"] = best.get("confidence","low"); pos["identified_score"] = best.get("score",0)
    chart = db.get_history(pid, days=180)
    return jsonify({"portfolio":portfolio,"positions":positions,"trades":db.get_trades(pid,limit=10),"identified":identified,"chart":chart})

@app.route("/api/portfolio/refresh-all", methods=["POST"])
def api_portfolio_refresh_all():
    import subprocess, threading
    def _run():
        try: subprocess.check_call([sys.executable,str(PROJ_ROOT/"scripts"/"portfolio_monitor.py"),"--identify"],cwd=PROJ_ROOT,timeout=300)
        except: pass
    threading.Thread(target=_run,daemon=True).start()
    return jsonify({"ok":True,"message":"刷新任务已后台启动"})

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()
    print(f"dashboard on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()