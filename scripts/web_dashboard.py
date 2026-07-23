"""
web_dashboard.py —— 东方财富实盘选手持仓/调仓实时看板

轻量 Flask 应用,单文件零模板目录,内嵌 HTML/JS。
后端读 SQLite(`data/crawl_data.db`),
并支持实时"按组合 ID 添加选手"(触发 polldirect 抓一次后再刷新页面)。

启动:
    python scripts/web_dashboard.py --port 5000 --host 0.0.0.0
打开:
    http://localhost:5000

路由:
    GET  /                    HTML 单页
    GET  /api/players         已抓选手列表 (zh_id / name / updated_at / n_pos / n_trades)
    GET  /api/positions?zh=…  指定 zh 的持仓行(最新 crawl_date)
    GET  /api/trades?zh=…     指定 zh 的调仓行(最新 crawl_date)
    POST /api/add             body: {"zh_id":"900235873"}  同步抓一次后返回结果
    POST /api/refresh-all     对所有选手立刻抓一轮
    POST /api/delete          body: {"zh_id":"900098256"}  从三表删除该选手全部记录
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
import threading
import time
from datetime import date
from pathlib import Path

from flask import Flask, request, jsonify, Response

PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))
from src.storage.sqlite_storage import SQLiteStorage  # noqa: E402
from src.storage.portfolio_db import PortfolioDB  # noqa: E402
from scripts.polldirect import poll_one, _post_detail, load_em_headers  # noqa: E402

DB_PATH = PROJ_ROOT / "data" / "crawl_data.db"
PORTFOLIO_DB_PATH = PROJ_ROOT / "data" / "portfolio.db"
ALERTS_LOG = PROJ_ROOT / "data" / "alerts.log"

app = Flask(__name__)
storage = SQLiteStorage(DB_PATH)
_poll_lock = threading.Lock()  # 保证同一时刻仅一个抓取在跑


# ----- helpers -----
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=3)
    c.row_factory = sqlite3.Row
    return c


# ----- HTML -----
HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>东方财富 · 投顾组合看板</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 0; background: #f0f2f5; color: #1f2937; }
  header { background: linear-gradient(135deg,#1e3a8a,#312e81); color: #fff;
           padding: 0 22px; display: flex; justify-content: space-between;
           align-items: center; height: 56px; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
  header .left { display: flex; align-items: center; gap: 20px; }
  header h1 { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: 0.3px; }
  .nav-tabs { display: flex; gap: 2px; background: rgba(255,255,255,0.1);
              border-radius: 8px; padding: 3px; }
  .nav-tab { padding: 5px 16px; border-radius: 6px; cursor: pointer;
             font-size: 13px; color: rgba(255,255,255,0.7); transition: all 0.2s;
             font-weight: 500; user-select: none; }
  .nav-tab:hover { color: #fff; background: rgba(255,255,255,0.1); }
  .nav-tab.active { background: #fff; color: #1e3a8a; font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
  header .bar { display: flex; gap: 10px; align-items: center; font-size: 12px; color: rgba(255,255,255,0.8); }
  header button { background: rgba(255,255,255,0.15); color: #fff; border: 1px solid rgba(255,255,255,0.2);
                  padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500;
                  transition: all 0.15s; backdrop-filter: blur(4px); }
  header button:hover { background: rgba(255,255,255,0.25); border-color: rgba(255,255,255,0.4); }
  header button:disabled { opacity: 0.4; cursor: wait; }
  .view { display: none; }
  .view.active { display: block; }

  /* ---------- Players view ---------- */
  #view-players main { display: grid; grid-template-columns: 270px 1fr; gap: 14px;
         padding: 14px; height: calc(100vh - 56px); }
  #view-players .col-left { background: #fff; border-radius: 10px; padding: 12px;
              overflow-y: auto; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  #view-players .col-right { display: grid; grid-template-rows: auto auto 1fr;
               gap: 12px; overflow: hidden; }
  .player { padding: 8px 10px; border-radius: 8px; cursor: pointer;
            display: flex; justify-content: space-between; align-items: center;
            border: 1px solid transparent; margin-bottom: 3px; }
  .player:hover { background: #f0f4ff; }
  .player.active { background: #e0eaff; border-color: #93c5fd; }
  .player .pid { font-weight: 600; font-size: 13px; }
  .player .pmeta { color: #9ca3af; font-size: 11px; margin-top: 2px; }
  .player .badge { background: #eef2ff; color: #4f46e5; padding: 2px 8px;
                   border-radius: 12px; font-size: 11px; font-weight: 500; white-space: nowrap; }
  .del-btn { background: #fef2f2; color: #dc2626; border: 0;
             width: 22px; height: 22px; border-radius: 50%;
             font-size: 14px; cursor: pointer; line-height: 1;
             display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
  .del-btn:hover { background: #fecaca; color: #991b1b; }
  .del-btn:disabled { opacity: 0.4; cursor: wait; }

  /* ---------- Shared tables ---------- */
  .card { background: #fff; border-radius: 10px; padding: 14px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  .card-header { display: flex; justify-content: space-between; align-items: center;
                 margin-bottom: 10px; }
  .card-header h3 { margin: 0; font-size: 14px; font-weight: 600; color: #374151; }
  .card-header small { color: #9ca3af; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 8px 10px; color: #6b7280; font-weight: 500;
       font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
       border-bottom: 1px solid #e5e7eb; background: #f9fafb; }
  td { padding: 7px 10px; border-bottom: 1px solid #f3f4f6; }
  tr:hover td { background: #fafbff; }
  .empty-state { color: #c0c4cc; padding: 24px; text-align: center; font-size: 13px; }
  .pos-up   { color: #dc2626; font-weight: 500; }
  .pos-down { color: #16a34a; font-weight: 500; }
  .tag-buy  { background: #fef2f2; color: #dc2626; padding: 2px 8px;
              border-radius: 4px; font-size: 11px; font-weight: 600; }
  .tag-sell { background: #f0fdf4; color: #16a34a; padding: 2px 8px;
              border-radius: 4px; font-size: 11px; font-weight: 600; }
  .form-row { display: flex; gap: 6px; margin: 6px 0 10px; }
  .form-row input { flex: 1; padding: 7px 10px; font-size: 13px;
                    border: 1px solid #d1d5db; border-radius: 6px; outline: none; }
  .form-row input:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
  .form-row button { padding: 7px 14px; background: #4f46e5; color: #fff;
                     border: 0; border-radius: 6px; cursor: pointer; font-size: 13px;
                     font-weight: 500; transition: background 0.15s; }
  .form-row button:hover { background: #4338ca; }
  .hint { color: #9ca3af; font-size: 11px; margin: 4px 2px 8px; }
  .alerts-box { background: #fff; border-radius: 10px; padding: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.06); max-height: 200px;
                overflow-y: auto; font-size: 12px; }
  .alerts-box h3 { font-size: 13px; margin: 0 0 8px; }
  .alerts-box li { padding: 4px 6px; border-bottom: 1px dashed #f3f4f6; color: #6b7280; }

  /* ---------- Portfolio view ---------- */
  #view-portfolios { padding: 16px; height: calc(100vh - 56px); overflow-y: auto;
                     background: #f0f2f5; }
  .pf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 1400px;
             margin: 0 auto; }
  @media (max-width: 900px) { .pf-grid { grid-template-columns: 1fr; } }
  .pf-card { background: #fff; border-radius: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
             overflow: hidden; transition: box-shadow 0.2s; }
  .pf-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
  .pf-head { padding: 18px 20px 14px; border-bottom: 1px solid #f3f4f6;
             display: flex; justify-content: space-between; align-items: flex-start; }
  .pf-head .info h2 { margin: 0; font-size: 16px; font-weight: 700; color: #111827; }
  .pf-head .info .advisor { color: #6b7280; font-size: 12px; margin-top: 2px; }
  .pf-head .meta { text-align: right; }
  .pf-head .meta .assets { font-size: 18px; font-weight: 700; color: #111827; }
  .pf-head .meta .assets-label { font-size: 11px; color: #9ca3af; }
  .pf-head .meta .return { font-size: 13px; font-weight: 600; margin-top: 2px; }
  .pf-stats { display: grid; grid-template-columns: repeat(3,1fr); gap: 0;
              border-bottom: 1px solid #f3f4f6; }
  .pf-stat { text-align: center; padding: 14px 10px; }
  .pf-stat + .pf-stat { border-left: 1px solid #f3f4f6; }
  .pf-stat .num { font-size: 20px; font-weight: 700; color: #1f2937; }
  .pf-stat .label { font-size: 11px; color: #9ca3af; margin-top: 2px; }
  .pf-section { padding: 14px 20px 18px; }
  .pf-section h4 { margin: 0 0 10px; font-size: 13px; font-weight: 600; color: #374151; }
  .pf-section h4 .badge { display: inline-block; background: #eef2ff; color: #4f46e5;
                          padding: 1px 8px; border-radius: 10px; font-size: 11px;
                          font-weight: 500; margin-left: 6px; }
  .pf-table { width: 100%; font-size: 12px; }
  .pf-table th { font-size: 10px; padding: 6px 8px; }
  .pf-table td { padding: 6px 8px; }
  .pf-table .code-mask { color: #9ca3af; font-family: monospace; font-size: 11px; }
  .pf-table .shares { text-align: right; font-variant-numeric: tabular-nums; }
  .pf-table .money { text-align: right; font-variant-numeric: tabular-nums; }
  .profit-badge { display: inline-block; padding: 1px 8px; border-radius: 10px;
                  font-size: 11px; font-weight: 500; }
  .profit-badge.up { background: #fef2f2; color: #dc2626; }
  .profit-badge.down { background: #f0fdf4; color: #16a34a; }
  .profit-badge.flat { background: #f3f4f6; color: #6b7280; }
  .conf-badge { display: inline-block; padding: 1px 8px; border-radius: 10px;
                font-size: 11px; font-weight: 500; }
  .conf-badge.high { background: #f0fdf4; color: #16a34a; }
  .conf-badge.medium { background: #fffbeb; color: #d97706; }
  .conf-badge.low { background: #fef2f2; color: #dc2626; }
  .pf-trade-item { display: flex; justify-content: space-between; align-items: center;
                   padding: 7px 0; border-bottom: 1px solid #f3f4f6; font-size: 12px; }
  .pf-trade-item:last-child { border-bottom: 0; }
  .pf-trade-item .left { display: flex; align-items: center; gap: 8px; }
  .pf-trade-item .time { color: #9ca3af; font-size: 11px; }
  .identified-card { display: inline-flex; align-items: center; gap: 8px;
                     background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px;
                     padding: 8px 12px; margin: 3px; font-size: 12px; }
  .identified-card .code { font-weight: 600; color: #1f2937; }
  .identified-card .name { color: #4b5563; }

  .pf-card .loading { padding: 30px; text-align: center; color: #9ca3af; font-size: 13px; }
  .pf-card .loading::after { content: "..."; animation: dots 1.2s infinite; }
  @keyframes dots { 0%,20% { content: "."; } 40% { content: ".."; } 60%,100% { content: "..."; } }
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
    <button id="refresh-btn" onclick="refreshAll()">↻ 刷新全部</button>
  </div>
  <div class="bar" id="header-bar-portfolios" style="display:none">
    <span id="pf-last-update">—</span>
    <button id="pf-refresh-btn" onclick="refreshPortfolios()">↻ 刷新数据</button>
  </div>
</header>

<!-- ==================== Players View ==================== -->
<div id="view-players" class="view active">
<main>
  <div class="col-left">
    <h3 style="font-size:13px;color:#374151;margin:2px 4px 10px;">添加选手</h3>
    <form class="form-row" onsubmit="addPlayer(event)">
      <input type="text" id="zh-input" placeholder="组合 ID (如 900235873)" required>
      <button type="submit">ADD</button>
    </form>
    <div class="hint">只需组合 ID 一个。
        <code>reqUserid</code> 实测 API 不强制,留空即可。</div>
    <h3 style="font-size:13px;color:#374151;margin:10px 4px 8px;">已跟踪选手 <span id="pcount" style="font-weight:400;color:#9ca3af;"></span></h3>
    <div id="player-list"></div>
  </div>

  <div class="col-right">
    <div class="card">
      <div class="card-header">
        <h3>当前持仓 <small id="pos-zh" style="color:#9ca3af;"></small></h3>
      </div>
      <table id="pos-table"><thead>
        <tr><th>代码</th><th>名称</th><th>成本价</th>
            <th>现价</th><th>盈亏%</th><th>仓位%</th><th>日期</th></tr></thead>
        <tbody></tbody></table>
    </div>
    <div class="card">
      <div class="card-header">
        <h3>最近调仓 <small id="trade-zh" style="color:#9ca3af;"></small></h3>
      </div>
      <table id="trade-table"><thead>
        <tr><th>日期</th><th>方向</th><th>代码</th><th>名称</th>
            <th>数量</th><th>价格</th><th>仓位</th></tr></thead>
        <tbody></tbody></table>
    </div>
    <div class="alerts-box">
      <h3>🚨 调仓告警流</h3>
      <ul id="alerts-list" style="list-style:none; margin:0; padding:0;"></ul>
    </div>
  </div>
</main>
</div>

<!-- ==================== Portfolios View ==================== -->
<div id="view-portfolios" class="view">
  <div class="pf-grid" id="pf-grid">
    <div class="pf-empty" style="grid-column:1/-1;">
      <strong>正在加载投顾组合数据...</strong>
    </div>
  </div>
</div>

<script>
  const HOST = location.origin.replace(/\/$/, "");
  let currentZh = null;

  // ---- Tab switching ----
  function switchView(name) {
    document.querySelectorAll(".nav-tab").forEach(t => t.classList.toggle("active", t.dataset.view === name));
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
    document.getElementById("header-bar-players").style.display = name === "players" ? "flex" : "none";
    document.getElementById("header-bar-portfolios").style.display = name === "portfolios" ? "flex" : "none";
    if (name === "portfolios") loadPortfolios();
  }

  // ==================== Players ====================

  async function loadPlayers() {
    const res = await fetch(HOST + "/api/players");
    const players = await res.json();
    const box = document.getElementById("player-list");
    box.innerHTML = "";
    document.getElementById("pcount").textContent = "(" + players.length + ")";
    if (!players.length) {
      box.innerHTML = '<div class="empty-state">数据库为空<br>添加一个组合 ID 开始抓</div>';
      return;
    }
    for (const p of players) {
      const div = document.createElement("div");
      div.className = "player" + (p.zh_id === currentZh ? " active" : "");
      div.onclick = () => selectPlayer(p.zh_id);
      const badge = (p.n_pos || 0) + "持/" + (p.n_trades || 0) + "调";
      const m = (p.updated_at || "").replace("T"," ").slice(0,16);
      div.innerHTML = `
        <div>
          <div class="pid">${p.zh_id} ${p.name ? '<span style="color:#6b7280;font-weight:400;">'+p.name+'</span>':''}</div>
          <div class="pmeta">${m || "—"}</div>
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <span class="badge">${badge}</span>
          <button class="del-btn" title="删除" onclick="deletePlayer(event,'${p.zh_id}')">&times;</button>
        </div>`;
      box.appendChild(div);
    }
  }

  async function deletePlayer(e, zh) {
    e.stopPropagation();
    if (!confirm("确认删除选手 " + zh + " ?")) return;
    const btn = e.currentTarget;
    btn.disabled = true; btn.textContent = "…";
    try {
      const res = await fetch(HOST + "/api/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({zh_id: zh}),
      });
      const r = await res.json();
      if (!r.ok) throw new Error(r.error || "failed");
      if (currentZh === zh) { currentZh = null; clearPlayerDetail(); }
      loadPlayers(); loadAlerts();
    } catch (err) {
      alert("删除失败: " + err.message);
    } finally {
      btn.disabled = false; btn.textContent = "×";
    }
  }
  function clearPlayerDetail() {
    document.getElementById("pos-zh").textContent = "";
    document.getElementById("trade-zh").textContent = "";
    document.querySelector("#pos-table tbody").innerHTML = "";
    document.querySelector("#trade-table tbody").innerHTML = "";
  }

  async function selectPlayer(zh) {
    currentZh = zh;
    document.getElementById("pos-zh").textContent = "• " + zh;
    document.getElementById("trade-zh").textContent = "• " + zh;
    loadPlayers();
    loadPositions(zh);
    loadTrades(zh);
  }

  async function loadPositions(zh) {
    const res = await fetch(HOST + "/api/positions?zh=" + encodeURIComponent(zh));
    const data = await res.json();
    const tb = document.querySelector("#pos-table tbody");
    if (!data.length) {
      tb.innerHTML = '<tr><td class="empty-state" colspan="7">暂无持仓</td></tr>';
      return;
    }
    tb.innerHTML = data.map(r => {
      const cls = (r.profit_ratio > 0) ? "pos-up" : "pos-down";
      const d = (r.crawl_date||"").slice(5);
      return `<tr>
        <td>${r.stock_code||""}</td>
        <td>${r.stock_name||""}</td>
        <td>${r.cost_price||""}</td>
        <td>${r.current_price||""}</td>
        <td class="${cls}">${r.profit_ratio??""}%</td>
        <td>${r.position_ratio??""}%</td>
        <td style="color:#9ca3af">${d}</td></tr>`;
    }).join("");
  }

  async function loadTrades(zh) {
    const res = await fetch(HOST + "/api/trades?zh=" + encodeURIComponent(zh));
    const data = await res.json();
    const tb = document.querySelector("#trade-table tbody");
    if (!data.length) {
      tb.innerHTML = '<tr><td class="empty-state" colspan="7">暂无调仓</td></tr>';
      return;
    }
    tb.innerHTML = data.map(r => {
      const tag = (r.direction === "buy") ? '<span class="tag-buy">买</span>'
                 : (r.direction === "sell") ? '<span class="tag-sell">卖</span>'
                 : r.direction;
      const dt = (r.trade_date || "").replace(/(\d{4})(\d{2})(\d{2})/,"$1-$2-$3");
      return `<tr>
        <td>${dt}</td>
        <td>${tag}</td>
        <td>${r.stock_code||""}</td>
        <td>${r.stock_name||""}</td>
        <td>${r.position_change||""}</td>
        <td>${r.position_value||""}</td>
        <td>${r.position_ratio||""}</td></tr>`;
    }).join("");
  }

  async function loadAlerts() {
    const res = await fetch(HOST + "/api/alerts");
    const data = await res.json();
    const ul = document.getElementById("alerts-list");
    if (!data.length) {
      ul.innerHTML = '<li class="empty-state" style="padding:8px;">无告警</li>';
      return;
    }
    ul.innerHTML = data.slice(0, 20).map(l => `<li>${l}</li>`).join("");
  }

  async function addPlayer(e) {
    e.preventDefault();
    const zh = document.getElementById("zh-input").value.trim();
    if (!zh) return;
    const btn = e.target.querySelector("button");
    btn.disabled = true; btn.textContent = "抓取中…";
    try {
      const res = await fetch(HOST + "/api/add", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({zh_id: zh}),
      });
      const r = await res.json();
      if (!r.ok) throw new Error(r.error || "failed");
      currentZh = zh;
      loadPlayers(); loadPositions(zh); loadTrades(zh); loadAlerts();
    } catch (err) {
      alert("添加失败:" + err.message);
    } finally {
      btn.disabled = false; btn.textContent = "ADD";
    }
  }

  async function refreshAll() {
    const btn = document.getElementById("refresh-btn");
    btn.disabled = true; btn.textContent = "抓取中…";
    try {
      await fetch(HOST + "/api/refresh-all", {method: "POST"});
      if (currentZh) { loadPositions(currentZh); loadTrades(currentZh); }
      loadPlayers(); loadAlerts();
      document.getElementById("last-update").textContent = "更新于 " + new Date().toLocaleTimeString();
    } catch (err) { alert("刷新失败:" + err); }
    finally { btn.disabled = false; btn.textContent = "↻ 刷新全部"; }
  }

  // ==================== Portfolios ====================

  async function refreshPortfolios() {
    const btn = document.getElementById("pf-refresh-btn");
    btn.disabled = true; btn.textContent = "刷新中…";
    document.getElementById("pf-last-update").textContent = "后台刷新中...";
    try {
      const res = await fetch(HOST + "/api/portfolio/refresh-all", {method: "POST"});
      const r = await res.json();
      if (!r.ok) throw new Error(r.error || "刷新失败");
      document.getElementById("pf-last-update").textContent = "刷新任务已启动，请稍后刷新页面";
      // 后台刷新完成后，用户手动刷新页面即可看到最新数据
    } catch (err) {
      alert("刷新失败: " + err.message);
      document.getElementById("pf-last-update").textContent = "刷新失败";
    } finally {
      btn.disabled = false; btn.textContent = "↻ 刷新数据";
    }
  }

  async function loadPortfolios() {
    const grid = document.getElementById("pf-grid");
    grid.innerHTML = '<div class="pf-empty" style="grid-column:1/-1;"><strong>加载中...</strong></div>';
    document.getElementById("pf-last-update").textContent = "刷新于 " + new Date().toLocaleTimeString();

    try {
      const res = await fetch(HOST + "/api/portfolio/summary");
      const data = await res.json();
      const portfolios = data.portfolios || [];

      if (!portfolios.length) {
        grid.innerHTML = '<div class="pf-empty" style="grid-column:1/-1;">' +
          '<strong>暂无投顾组合数据</strong><br><span style="color:#bbb;">请先运行 python scripts/portfolio_monitor.py --identify</span></div>';
        return;
      }

      grid.innerHTML = "";
      for (const p of portfolios) {
        const card = document.createElement("div");
        card.className = "pf-card";
        card.innerHTML = buildPortfolioCard(p);
        grid.appendChild(card);

        // Load detail in background
        loadPortfolioDetail(p.id, card);
      }
    } catch (err) {
      grid.innerHTML = '<div class="pf-empty" style="grid-column:1/-1;">' +
        '<strong>加载失败: ' + err.message + '</strong></div>';
    }
  }

  function buildPortfolioCard(p) {
    const totalReturn = (p.total_return || 0);
    const returnCls = totalReturn >= 0 ? "pos-up" : "pos-down";
    const returnStr = (totalReturn * 100).toFixed(2) + "%";
    const assets = (p.total_assets || 0).toLocaleString("zh-CN", {minimumFractionDigits:2});

    return `
      <div class="pf-head">
        <div class="info">
          <h2>#${p.id} ${p.name || "—"}</h2>
          <div class="advisor">👤 ${p.advisor || "—"}</div>
        </div>
        <div class="meta">
          <div class="assets">¥${assets}</div>
          <div class="assets-label">总资产</div>
          <div class="return ${returnCls}">总收益 ${returnStr}</div>
        </div>
      </div>
      <div class="pf-stats">
        <div class="pf-stat"><div class="num" id="pf-pos-count-${p.id}">—</div><div class="label">持仓</div></div>
        <div class="pf-stat"><div class="num" id="pf-trade-count-${p.id}">—</div><div class="label">调仓</div></div>
        <div class="pf-stat"><div class="num" id="pf-identified-count-${p.id}">—</div><div class="label">已识别</div></div>
      </div>
      <div id="pf-detail-${p.id}"><div class="loading">加载明细</div></div>`;
  }

  async function loadPortfolioDetail(pid, cardEl) {
    try {
      const res = await fetch(HOST + "/api/portfolio/" + pid);
      const data = await res.json();
      if (!data.portfolio) {
        document.getElementById("pf-detail-" + pid).innerHTML = '<div class="pf-empty">无数据</div>';
        return;
      }

      // Update stats
      document.getElementById("pf-pos-count-" + pid).textContent = (data.positions || []).length;
      document.getElementById("pf-trade-count-" + pid).textContent = (data.trades || []).length;
      document.getElementById("pf-identified-count-" + pid).textContent = (data.identified || []).length;

      // Build detail
      let html = "";

      // Positions with integrated identification
      html += '<div class="pf-section">';
      html += '<h4>持仓明细 <span class="badge">' + (data.positions || []).length + ' 只</span></h4>';
      if (data.positions && data.positions.length) {
        html += '<table class="pf-table"><thead><tr>' +
          '<th>代码</th><th>名称</th><th>数量</th><th>现价</th><th>成本价</th><th>市值</th><th>盈亏</th><th>盈亏比</th><th>仓位%</th><th>备注</th></tr></thead><tbody>';
        for (const pos of data.positions) {
          const profit = pos.profit || 0;
          const prCls = profit >= 0 ? "up" : "down";
          const prStr = profit >= 0 ? "+" + profit.toFixed(2) : profit.toFixed(2);
          const prRatio = pos.profit_ratio || (profit >= 0 ? "+" : "") + profit.toFixed(2);
          const posRatio = pos.position_ratio || 0;

          const code = pos.stock_code || "";
          const name = pos.stock_name || "";
          const isMasked = code.includes("***") || code.includes("****");
          // 检查 remarks 字段（JSON 数组或空字符串）
          const remarks = pos.remarks || "";
          let remarksList = [];
          try { remarksList = JSON.parse(remarks); } catch(e) {}
          const hasRemarksCandidates = Array.isArray(remarksList) && remarksList.length > 0;

          const idCode = pos.identified_code || "";
          const idName = pos.identified_name || "";
          const idConf = pos.identified_confidence || "";
          const isHighConf = idConf === "high";

          // Display code/name: high confidence -> show real name, otherwise mask
          var displayCode, displayName, remark;
          var idScore = pos.identified_score || 0;
          if (hasRemarksCandidates) {
            // 收盘价精确匹配发现多只候选，显示在备注列
            displayCode = code.replace(/\*/g,'<span style="color:#d1d5db;">*</span>');
            displayName = '<span style="color:#d1d5db;">' + escapeHtml(name) + '</span>';
            remark = '<span style="color:#d97706;font-size:11px;">⚠️ 多只候选: ' +
              remarksList.map(function(r) { return escapeHtml(r.code) + ' ' + escapeHtml(r.name); }).join(', ') +
              '</span>';
          } else if (isMasked && isHighConf) {
            displayCode = escapeHtml(idCode);
            displayName = escapeHtml(idName);
            remark = '<span style="color:#16a34a;font-size:11px;">\u2713 ' + idScore.toFixed(0) + '</span>';
          } else if (isMasked && idCode) {
            displayCode = code.replace(/\*/g,'<span style="color:#d1d5db;">*</span>');
            displayName = '<span style="color:#d1d5db;">' + escapeHtml(name) + '</span>';
            remark = '<span style="color:#d97706;font-size:11px;">\u2753 ' + escapeHtml(idCode) + ' ' + escapeHtml(idName) + ' [' + idScore.toFixed(0) + ']</span>';
          } else if (isMasked) {
            displayCode = code.replace(/\*/g,'<span style="color:#d1d5db;">*</span>');
            displayName = '<span style="color:#d1d5db;">' + escapeHtml(name) + '</span>';
            remark = '<span style="color:#9ca3af;">\u2014</span>';
          } else {
            displayCode = escapeHtml(code);
            displayName = escapeHtml(name);
            remark = '<span style="color:#9ca3af;">\u2014</span>';
          }

          const curPx = pos.current_price_calc || 0;
          html += '<tr>' +
            '<td>' + displayCode + '</td>' +
            '<td>' + displayName + '</td>' +
            '<td class="shares">' + (pos.shares || 0) + '</td>' +
            '<td class="money">' + curPx.toFixed(2) + '</td>' +
            '<td class="money">' + (pos.cost_price || 0).toFixed(2) + '</td>' +
            '<td class="money">' + (pos.current_value || 0).toFixed(2) + '</td>' +
            '<td class="money ' + prCls + '">' + prStr + '</td>' +
            '<td><span class="profit-badge ' + prCls + '">' + prRatio + '</span></td>' +
            '<td class="shares">' + posRatio.toFixed(1) + '</td>' +
            '<td style="font-size:11px;">' + remark + '</td>' +
            '</tr>';
        }
        html += '</tbody></table>';
      } else {
        html += '<div class="pf-empty">暂无持仓数据</div>';
      }
      html += '</div>';

      // Trades (last 10 records from dealRecord API)
      if (data.trades && data.trades.length) {
        html += '<div class="pf-section" style="padding-top:0;">';
        html += '<h4>最近调仓 <span class="badge">' + data.trades.length + ' 条</span></h4>';
        html += '<table class="pf-table"><thead><tr>' +
          '<th>方向</th><th>时间</th><th>代码</th><th>名称</th><th>价格</th><th>数量</th><th>金额</th><th>参考</th></tr></thead><tbody>';
        for (const t of data.trades) {
          const isBuy = (t.direction || "").includes("买");
          const tagCls = isBuy ? "tag-buy" : "tag-sell";
          const tagText = isBuy ? "买入" : "卖出";
          const code = t.stock_code || "";
          const name = t.stock_name || "";
          const masked = code.includes("*");
          const price = t.price || 0;
          const qty = t.quantity || 0;
          const amt = t.amount || 0;
          const suggestPx = t.suggest_price || 0;
          // 当cjjg被屏蔽时，用suggestPrice推算
          var displayPrice, displayQty;
          if (price > 0 && qty > 0) {
            displayPrice = price.toFixed(2);
            displayQty = qty;
          } else if (suggestPx > 0 && amt > 0) {
            // 从建议价和成交金额推算
            var estQty = Math.round(amt / suggestPx);
            displayPrice = '<span title="建议价">' + suggestPx.toFixed(2) + '</span>';
            displayQty = estQty;
          } else {
            displayPrice = '<span style="color:#d1d5db;">***</span>';
            displayQty = '<span style="color:#d1d5db;">***</span>';
          }
          html += '<tr>' +
            '<td><span class="' + tagCls + '">' + tagText + '</span></td>' +
            '<td style="color:#9ca3af;font-size:11px;">' + (t.trade_time || "").slice(0,16) + '</td>' +
            '<td class="code-mask">' + (masked ? code.replace(/\*/g,'<span style="color:#d1d5db;">*</span>') : escapeHtml(code)) + '</td>' +
            '<td>' + (masked ? '<span style="color:#d1d5db;">' + escapeHtml(name) + '</span>' : escapeHtml(name)) + '</td>' +
            '<td class="money">' + displayPrice + '</td>' +
            '<td class="shares">' + displayQty + '</td>' +
            '<td class="money">' + amt.toFixed(0) + '</td>' +
            '<td style="font-size:11px;color:#9ca3af;">' + escapeHtml(t.price_range || '') + '</td>' +
            '</tr>';
        }
        html += '</tbody></table>';
        html += '</div>';
      } else {
        html += '<div class="pf-section" style="padding-top:0;">';
        html += '<h4>最近调仓</h4><div class="pf-empty">暂无调仓数据</div></div>';
      }

      // Profit chart
      if (data.chart && data.chart.length > 5) {
        html += '<div class="pf-section" style="padding-top:0;">';
        html += '<h4>收益走势 <span class="badge">' + data.chart.length + ' 个交易日</span></h4>';
        html += '<div style="position:relative;height:180px;margin:8px 0;">';
        html += buildMiniChart(data.chart);
        html += '</div></div>';
      }

      document.getElementById("pf-detail-" + pid).innerHTML = html;

    } catch (err) {
      document.getElementById("pf-detail-" + pid).innerHTML =
        '<div class="pf-empty">加载失败: ' + err.message + '</div>';
    }
  }

  function escapeHtml(s) {
    if (!s) return "";
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ---- Mini SVG Chart ----
  function buildMiniChart(data) {
    if (!data || data.length < 2) return '<div style="color:#9ca3af;text-align:center;padding:20px;">数据不足</div>';
    
    const w = 600, h = 160, pad = {t:16, r:16, b:24, l:50};
    const cw = w - pad.l - pad.r, ch = h - pad.t - pad.b;
    
    // Reverse to chronological order
    var points = data.slice().reverse();
    
    // Extract values
    var assets = points.map(function(p) { return p.asset_value || 0; });
    var hs300 = points.map(function(p) { return p.hs300_value || 0; });
    
    // Normalize to percentage change from first value
    var baseAsset = assets[0] || 1;
    var baseHs = hs300[0] || 1;
    var assetPct = assets.map(function(v) { return (v - baseAsset) / baseAsset * 100; });
    var hsPct = hs300.map(function(v) { return (v - baseHs) / baseHs * 100; });
    
    // Find range
    var allVals = assetPct.concat(hsPct);
    var minV = Math.min.apply(null, allVals);
    var maxV = Math.max.apply(null, allVals);
    var range = maxV - minV || 1;
    var padR = range * 0.12;
    minV -= padR; maxV += padR;
    
    function x(i) { return pad.l + (i / (points.length - 1)) * cw; }
    function y(v) { return pad.t + ch - ((v - minV) / (maxV - minV)) * ch; }
    
    function linePath(values) {
      return values.map(function(v, i) {
        return (i === 0 ? 'M' : 'L') + x(i).toFixed(1) + ',' + y(v).toFixed(1);
      }).join('');
    }
    
    // Format date label
    function fmtDate(d) {
      var s = d || '';
      return s.length >= 8 ? s.slice(2,4) + '/' + s.slice(4,6) : s;
    }
    
    var html = '<svg width="100%" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" style="font-size:10px;overflow:visible;">';
    
    // Grid lines (5 horizontal)
    for (var gi = 0; gi <= 4; gi++) {
      var gy = minV + (maxV - minV) * (gi / 4);
      var gyPx = y(gy);
      html += '<line x1="' + pad.l + '" y1="' + gyPx + '" x2="' + (w-pad.r) + '" y2="' + gyPx + '" stroke="#f0f0f0" stroke-width="1"/>';
      html += '<text x="' + (pad.l-4) + '" y="' + (gyPx+3) + '" text-anchor="end" fill="#9ca3af">' + gy.toFixed(1) + '%</text>';
    }
    
    // Date labels (start, middle, end)
    var labelIndices = [0, Math.floor(points.length/2), points.length-1];
    for (var li = 0; li < labelIndices.length; li++) {
      var idx = labelIndices[li];
      html += '<text x="' + x(idx) + '" y="' + (h-4) + '" text-anchor="middle" fill="#9ca3af">' + fmtDate(points[idx].record_date) + '</text>';
    }
    
    // HS300 line (gray)
    html += '<path d="' + linePath(hsPct) + '" fill="none" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4,3"/>';
    // Asset line (blue)
    html += '<path d="' + linePath(assetPct) + '" fill="none" stroke="#4f46e5" stroke-width="2"/>';
    
    // Legend
    var lastAsset = assetPct[assetPct.length-1];
    var lastHs = hsPct[hsPct.length-1];
    html += '<rect x="' + (w-140) + '" y="4" width="136" height="38" rx="4" fill="white" stroke="#e5e7eb" stroke-width="1"/>';
    html += '<circle cx="' + (w-130) + '" cy="14" r="4" fill="#4f46e5"/>';
    html += '<text x="' + (w-120) + '" y="18" fill="#374151">组合收益 <tspan fill="' + (lastAsset>=0?'#dc2626':'#16a34a') + '">' + (lastAsset>=0?'+':'') + lastAsset.toFixed(2) + '%</tspan></text>';
    html += '<circle cx="' + (w-130) + '" cy="30" r="4" fill="#d1d5db"/>';
    html += '<text x="' + (w-120) + '" y="34" fill="#9ca3af">沪深300 <tspan>' + (lastHs>=0?'+':'') + lastHs.toFixed(2) + '%</tspan></text>';
    
    html += '</svg>';
    return html;
  }

  // ---- Boot ----
  loadPlayers(); loadAlerts();
  document.getElementById("last-update").textContent = "页面加载于 " + new Date().toLocaleTimeString();
  setInterval(loadAlerts, 30000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return Response(HTML_PAGE, mimetype="text/html; charset=utf-8")


# ----- API -----
@app.route("/api/players")
def api_players():
    with _conn() as c:
        rows = c.execute("""
            SELECT p.zh_id, p.name, p.updated_at, p.total_return, p.daily_return
            FROM players p
            ORDER BY p.updated_at DESC
        """).fetchall()
        all_zh = [r["zh_id"] for r in rows]
        counts = {"pos": {}, "trd": {}}
        if all_zh:
            ph = ",".join("?" * len(all_zh))
            pos = c.execute(f"SELECT zh_id, COUNT(*) n FROM positions GROUP BY zh_id HAVING zh_id IN ({ph})", all_zh).fetchall()
            trd = c.execute(f"SELECT zh_id, COUNT(*) n FROM trades GROUP BY zh_id HAVING zh_id IN ({ph})", all_zh).fetchall()
            counts = {
                "pos": {r["zh_id"]: r["n"] for r in pos},
                "trd": {r["zh_id"]: r["n"] for r in trd},
            }
        return jsonify([{
            "zh_id": r["zh_id"],
            "name": r["name"],
            "updated_at": str(r["updated_at"]) if r["updated_at"] else "",
            "total_return": r["total_return"],
            "daily_return": r["daily_return"],
            "n_pos": counts["pos"].get(r["zh_id"], 0),
            "n_trades": counts["trd"].get(r["zh_id"], 0),
        } for r in rows])


@app.route("/api/positions")
def api_positions():
    zh = (request.args.get("zh") or "").strip()
    if not zh:
        return jsonify([])
    # 取最新 crawl_date
    with _conn() as c:
        r = c.execute("SELECT MAX(crawl_date) d FROM positions WHERE zh_id=?", (zh,)).fetchone()
        if not r or not r["d"]:
            return jsonify([])
        d = r["d"]
        rows = c.execute("""
            SELECT stock_code, stock_name, cost_price, current_price,
                   profit_ratio, position_ratio, crawl_date
            FROM positions
            WHERE zh_id=? AND crawl_date=?
            ORDER BY position_ratio DESC
        """, (zh, d)).fetchall()
        return jsonify([dict(r) for r in rows])
        # 注: 我们的 SQLiteStorage schema 没存 sector, 这里依赖 sector 字段会为空
        # 前端可省略显示,或后续 schema 扩展


@app.route("/api/trades")
def api_trades():
    zh = (request.args.get("zh") or "").strip()
    if not zh:
        return jsonify([])
    with _conn() as c:
        r = c.execute("SELECT MAX(crawl_date) d FROM trades WHERE zh_id=?", (zh,)).fetchone()
        if not r or not r["d"]:
            return jsonify([])
        d = r["d"]
        rows = c.execute("""
            SELECT stock_code, stock_name, direction, trade_date,
                   position_change, position_value, position_ratio, crawl_date
            FROM trades
            WHERE zh_id=? AND crawl_date=?
            ORDER BY trade_date DESC, id DESC
        """, (zh, d)).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route("/api/alerts")
def api_alerts():
    if not ALERTS_LOG.exists():
        return jsonify([])
    lines = ALERTS_LOG.read_text(encoding="utf-8").splitlines()
    return jsonify(lines[-50:])


@app.route("/api/add", methods=["POST"])
def api_add():
    data = request.get_json(force=True) or {}
    zh = str(data.get("zh_id", "") or "").strip()
    if not zh or not zh.isdigit():
        return jsonify({"ok": False, "error": "zh_id 必须是纯数字字符串"}), 400
    if not _poll_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "已有抓取任务正在跑,稍后再试"}), 409
    try:
        crawl_date = date.today().isoformat()
        r = poll_one(storage, zh, crawl_date=crawl_date,
                     alerts_log=ALERTS_LOG, verbose=False)
        return jsonify({"ok": r.get("ok", False), "zh_id": zh, "result": r})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        _poll_lock.release()


@app.route("/api/delete", methods=["POST"])
def api_delete():
    """删除选手: 从 players / positions / trades 三表里全部清掉。
    body: {"zh_id":"900098256"} """
    data = request.get_json(force=True) or {}
    zh = str(data.get("zh_id", "") or "").strip()
    if not zh:
        return jsonify({"ok": False, "error": "zh_id 必填"}), 400
    try:
        with _conn() as c:
            n_pos = c.execute("SELECT COUNT(*) FROM positions WHERE zh_id=?", (zh,)).fetchone()[0]
            n_trd = c.execute("SELECT COUNT(*) FROM trades WHERE zh_id=?", (zh,)).fetchone()[0]
            n_pl  = c.execute("SELECT COUNT(*) FROM players WHERE zh_id=?", (zh,)).fetchone()[0]
            c.execute("DELETE FROM positions WHERE zh_id=?", (zh,))
            c.execute("DELETE FROM trades WHERE zh_id=?", (zh,))
            c.execute("DELETE FROM players WHERE zh_id=?", (zh,))
        return jsonify({"ok": True, "zh_id": zh,
                        "deleted": {"players": n_pl, "positions": n_pos, "trades": n_trd}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/refresh-all", methods=["POST"])
def api_refresh_all():
    if not _poll_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "已有抓取任务正在跑"}), 409
    try:
        with _conn() as c:
            zh_ids = [r["zh_id"] for r in c.execute(
                "SELECT DISTINCT zh_id FROM positions UNION SELECT zh_id FROM trades"
            ).fetchall()]
        crawl_date = date.today().isoformat()
        results = []
        for zh in zh_ids:
            results.append(poll_one(storage, zh, crawl_date=crawl_date,
                                    alerts_log=ALERTS_LOG, verbose=False))
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        _poll_lock.release()


# ----- Portfolio Tracker API -----

@app.route("/api/portfolio/summary")
def api_portfolio_summary():
    db = PortfolioDB(PORTFOLIO_DB_PATH)
    return jsonify({"summary": db.summary(), "portfolios": [
        db.get_portfolio(pid) for pid in [278, 413] if db.get_portfolio(pid)
    ]})

@app.route("/api/portfolio/<int:pid>")
def api_portfolio_detail(pid):
    db = PortfolioDB(PORTFOLIO_DB_PATH)
    portfolio = db.get_portfolio(pid)
    if not portfolio:
        return jsonify({"portfolio": None, "positions": [], "trades": [], "identified": []})
    total_assets = portfolio.get("total_assets") or 0

    positions = db.get_positions(pid)
    identified = db.get_identified(pid)

    for pos in positions:
        # Position ratio & current price
        val = pos.get("current_value") or 0
        shares = pos.get("shares", 0) or 0
        pos["position_ratio"] = round(val / total_assets * 100, 2) if total_assets > 0 else 0
        pos["current_price_calc"] = round(val / shares, 4) if shares > 0 else 0

        # Match by price proximity (for same-prefix multi-position disambiguation)
        prefix = (pos.get("stock_code") or "")[:3]
        unit_price = val / shares if shares > 0 else 0
        candidates = [i for i in identified if (i.get("stock_code") or "").startswith(prefix)]

        if candidates:
            # Sort by match_price proximity to unit_price, then by score
            def sort_key(idf):
                mp = idf.get("match_price") or idf.get("current_price") or 0
                price_diff = abs(mp - unit_price) / unit_price if unit_price > 0 and mp > 0 else 999
                return (price_diff, -(idf.get("score") or 0))
            candidates.sort(key=sort_key)
            best = candidates[0]
            pos["identified_code"] = best.get("stock_code")
            pos["identified_name"] = best.get("stock_name")
            pos["identified_confidence"] = best.get("confidence", "low")
            pos["identified_diff"] = best.get("match_diff_pct")
            pos["identified_score"] = best.get("score", 0)

    chart = db.get_history(pid, days=180)
    return jsonify({
        "portfolio": portfolio,
        "positions": positions,
        "trades": db.get_trades(pid, limit=10),
        "identified": identified,
        "chart": chart,
    })

@app.route("/api/portfolio/refresh-all", methods=["POST"])
def api_portfolio_refresh_all():
    """一键刷新全部组合（持仓+识别+调仓+走势）—— 后台异步执行"""
    import subprocess, sys, threading

    def _run_refresh():
        try:
            subprocess.check_call(
                [sys.executable, str(PROJ_ROOT / "scripts" / "portfolio_monitor.py"),
                 "--identify"],
                cwd=PROJ_ROOT, timeout=300,
            )
            logger.info("Portfolio refresh completed successfully")
        except subprocess.TimeoutExpired:
            logger.error("Portfolio refresh timed out (>5min)")
        except Exception as e:
            logger.error(f"Portfolio refresh failed: {e}")

    thread = threading.Thread(target=_run_refresh, daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "刷新任务已后台启动，请稍后刷新页面查看结果"})

@app.route("/api/portfolio/<int:pid>/refresh", methods=["POST"])
def api_portfolio_refresh(pid):
    """手动触发指定组合的重新抓取 —— 后台异步执行"""
    import subprocess, threading

    def _run_refresh(pid):
        try:
            subprocess.check_call(
                [sys.executable, str(PROJ_ROOT / "scripts" / "portfolio_monitor.py"),
                 "--identify", "--portfolio", str(pid)],
                cwd=PROJ_ROOT, timeout=300,
            )
            logger.info(f"Portfolio #{pid} refresh completed")
        except subprocess.TimeoutExpired:
            logger.error(f"Portfolio #{pid} refresh timed out (>5min)")
        except Exception as e:
            logger.error(f"Portfolio #{pid} refresh failed: {e}")

    thread = threading.Thread(target=_run_refresh, args=(pid,), daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": f"组合 #{pid} 刷新任务已后台启动"})

# ----- main -----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()
    print(f"dashboard on http://{args.host}:{args.port}  (DB: {DB_PATH})")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()