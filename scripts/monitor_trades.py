"""
选手调仓监控脚本
================
监控关注的选手在 A 股交易时段的调仓行为。
每 2-4 分钟随机间隔轮询一次，检测到变动后写入告警队列。

用法:
    python scripts/monitor_trades.py

通过 Hermes 配置定时任务，在交易时段运行。
"""
import json
import random
import sqlite3
import sys
import time as _time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
import uuid

from src.utils.logger import setup_logger

logger = setup_logger()

# ── 配置 ──
DB_PATH = ROOT / "data" / "crawl_data.db"
EM_API = "https://emdcspzhapi.eastmoney.com/rtV2"
EM_HEADERS_FILE = ROOT / "config" / "em_headers.json"
ALERTS_FILE = ROOT / "data" / "alerts.json"  # 兼容 Harmers 读取

# A 股交易时段
MORNING_START = dtime(9, 30)
MORNING_END = dtime(11, 30)
AFTERNOON_START = dtime(13, 0)
AFTERNOON_END = dtime(15, 0)


# ── 工具函数 ──

def is_market_open() -> bool:
    """判断当前是否在 A 股交易时段"""
    now = datetime.now()
    if now.weekday() >= 5:  # 周末
        return False
    t = now.time()
    return (MORNING_START <= t <= MORNING_END) or (AFTERNOON_START <= t <= AFTERNOON_END)


def load_em_headers() -> dict:
    h = {
        "Accept-Encoding": "gzip", "Content-Type": "application/json; charset=UTF-8",
        "EM-CHL": "taobao45", "EM-CT": "", "EM-OS": "Android",
        "EM-PA": "1", "EM-SL": "0", "EM-UT": "",
        "User-Agent": "okhttp/3.12.13", "Host": "emdcspzhapi.eastmoney.com",
    }
    if EM_HEADERS_FILE.exists():
        cfg = json.loads(EM_HEADERS_FILE.read_text(encoding="utf-8"))
        for k in ("EM-MD", "EM-GT", "EM-GV", "EM-VER", "EM-PKG"):
            if cfg.get(k):
                h[k] = cfg[k]
    return h


def fetch_rtv2(zh_id: str) -> Optional[dict]:
    """调用 rtV2 API 获取选手最新数据"""
    headers = load_em_headers()
    body = {
        "args": {"reqUserid": "", "zh": zh_id},
        "clientType": "cfzq", "method": "combination_detail_97",
        "client": "android", "appKey": "eastmoney",
        "clientVersion": "10.13.5",
        "randomCode": str(uuid.uuid4()),
        "timestamp": int(_time.time() * 1000),
    }
    try:
        r = requests.post(EM_API, json=body, headers=headers, timeout=15)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != 0:
            logger.warning(f"API error zh={zh_id}: {j.get('message')}")
            return None
        return j["data"]
    except Exception as e:
        logger.warning(f"Failed to fetch {zh_id}: {e}")
        return None


def init_db():
    """初始化数据库表"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_snapshots (
                zh_id TEXT PRIMARY KEY,
                positions_json TEXT,
                trades_json TEXT,
                snapshot_time TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zh_id TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent INTEGER DEFAULT 0
            )
        """)


def get_followed_players() -> list:
    """获取关注列表"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT zh_id FROM followed_players").fetchall()
        return [r[0] for r in rows]


def get_snapshot(zh_id: str) -> Optional[dict]:
    """获取上次快照"""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT positions_json, trades_json FROM player_snapshots WHERE zh_id=?",
            (zh_id,)
        ).fetchone()
        if row:
            return {
                "positions": json.loads(row[0]) if row[0] else [],
                "trades": json.loads(row[1]) if row[1] else [],
            }
        return None


def save_snapshot(zh_id: str, positions: list, trades: list):
    """保存快照"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO player_snapshots (zh_id, positions_json, trades_json, snapshot_time) VALUES (?, ?, ?, ?)",
            (zh_id, json.dumps(positions, ensure_ascii=False), json.dumps(trades, ensure_ascii=False), datetime.now().isoformat()),
        )


def save_alert(zh_id: str, message: str):
    """保存告警"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO monitor_alerts (zh_id, message) VALUES (?, ?)",
            (zh_id, message),
        )
    # 同时写入 alerts.json 供 Harmers 读取
    alerts = []
    if ALERTS_FILE.exists():
        try:
            alerts = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    alerts.append({"zh_id": zh_id, "message": message, "time": datetime.now().isoformat()})
    ALERTS_FILE.write_text(json.dumps(alerts[-50:], ensure_ascii=False, indent=2), encoding="utf-8")


def detect_changes(zh_id: str, name: str, current_positions: list, current_trades: list) -> Optional[str]:
    """检测持仓/调仓变动，返回通知消息（无变动返回 None）"""
    snapshot = get_snapshot(zh_id)
    if not snapshot:
        # 首次监控，无快照，保存后跳过
        save_snapshot(zh_id, current_positions, current_trades)
        return None

    old_trades = snapshot.get("trades", [])
    old_positions = snapshot.get("positions", [])

    # 构建索引
    old_trade_keys = {(t.get("stock_code", ""), t.get("trade_date", "")) for t in old_trades if t.get("stock_code")}
    new_trade_keys = {(t.get("stock_code", ""), t.get("trade_date", "")) for t in current_trades if t.get("stock_code")}

    new_trades = [t for t in current_trades if (t.get("stock_code", ""), t.get("trade_date", "")) not in old_trade_keys]

    if not new_trades:
        return None

    # 构建通知
    lines = [f"📢 选手调仓提醒", f"", f"选手: {name} ({zh_id})", ""]

    for t in new_trades:
        stock_name = t.get("stock_name", "")
        stock_code = str(t.get("stock_code", ""))
        buy_qty = t.get("buy_qty", "0")
        sell_qty = t.get("sell_qty", "0")

        # 判断方向
        if buy_qty not in ("0", "0.0", 0, "0.00", "", "--"):
            direction = "买入"
            qty = buy_qty
            pos = t.get("buy_position", "--")
            price = t.get("buy_price", "--")
        else:
            direction = "卖出"
            qty = sell_qty
            pos = t.get("sell_position", "--")
            price = t.get("sell_price", "--")

        lines.append(f"{stock_name} {stock_code} {direction} 笔数 {qty}笔， 交易仓位 {pos} 均价 {price}")

    # 当前全部持仓
    lines.append("📦 当前持仓:")
    for i, p in enumerate(current_positions, 1):
        lines.append(f"  {i}. {p.get('stock_name','')}({p.get('stock_code','')}) "
                     f"成本{p.get('cost_price','')} 现价{p.get('current_price','')} "
                     f"盈亏{p.get('profit_ratio','')}% 仓位{p.get('position_ratio','')}%")

    return "\n".join(lines)


def poll_once():
    """单次轮询：检查所有关注选手"""
    if not is_market_open():
        logger.info("非交易时段，跳过")
        return

    players = get_followed_players()
    if not players:
        logger.info("关注列表为空")
        return

    logger.info(f"轮询 {len(players)} 名关注选手...")

    for zh_id in players:
        data = fetch_rtv2(zh_id)
        if not data:
            logger.warning(f"获取 {zh_id} 数据失败，跳过")
            continue

        detail = data.get("detail", {})
        name = detail.get("zuheName") or detail.get("uidNick") or zh_id

        # 提取持仓和调仓
        positions = []
        for p in (data.get("position") or []):
            positions.append({
                "stock_code": str(p.get("__code", "")),
                "stock_name": p.get("__name", ""),
                "cost_price": p.get("cbj"),
                "current_price": p.get("__zxjg"),
                "profit_ratio": p.get("webYkRate"),
                "position_ratio": p.get("holdPos") or p.get("positionRateDetail"),
            })

        trades = []
        for t in (data.get("tradeSummary") or []):
            # 从 stkMktCode 提取纯数字代码: "SZ001309" → "001309"
            raw_code = str(t.get("stkMktCode", ""))
            code = raw_code[2:] if len(raw_code) > 2 else raw_code
            trades.append({
                "stock_code": code,
                "stock_name": t.get("stkName", ""),
                "trade_date": t.get("tzrq", ""),
                "buy_qty": t.get("lshj_mr", "0"),
                "buy_position": t.get("cwhj_mr", "--"),
                "buy_price": t.get("cjjg_mr", "--"),
                "sell_qty": t.get("lshj_mc", "0"),
                "sell_position": t.get("cwhj_mc", "--"),
                "sell_price": t.get("cjjg_mc", "--"),
            })

        # 检测变动
        message = detect_changes(zh_id, name, positions, trades)
        if message:
            logger.info(f"检测到 {name} 调仓变动")
            save_alert(zh_id, message)
            print(f"\n{message}\n{'-'*40}")

        # 更新快照
        save_snapshot(zh_id, positions, trades)

        # 间隔 2 秒避免被拉黑
        _time.sleep(2)


def main():
    logger.info("=" * 50)
    logger.info("选手调仓监控启动")
    logger.info("=" * 50)

    init_db()

    while True:
        if is_market_open():
            poll_once()
            # 随机 2-4 分钟间隔
            interval = random.randint(120, 240)
            logger.info(f"下次轮询在 {interval} 秒后")
            _time.sleep(interval)
        else:
            # 非交易时段，每 5 分钟检查一次是否开盘
            logger.info("非交易时段，5分钟后重试")
            _time.sleep(300)


if __name__ == "__main__":
    main()