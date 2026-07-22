"""
polldirect.py —— 东方财富证券 APP 直连 API 轮询器

无需 LDPlayer / mitm / sign。一次 POST 调用 emdcspzhapi/rtV2:
    method=combination_detail_97    body={"args":{"reqUserid":"","zh":...}}
即可一次拿全:
  - detail          选手完整信息(名字/收益/胜率/最大回撤 等)
  - position[]      持仓数组(与旧 rtV1 schema 兼容 __code/__name/cbj/__zxjg/holdPos)
  - tradeSummary[]  最近 10 条调仓(与旧 rtV1 schema 兼容: lshj_mr/cwhj_mr/lshj_mc/cwhj_mc)
  - tendency/dimensions/evaluation/label/tendencySummary

参数:
  --loop             持续轮询 (否则只跑一次)
  --interval N       轮询间隔秒, 默认 300 (5 分钟)
  --zhids FILE       zhid 列表文件, 默认 config/zhids.txt
  --db PATH          SQLite 路径, 默认 data/crawl_data.db
  --alerts PATH      告警日志路径, 默认 data/alerts.log
  --raw-dir DIR      原始 API 响应存档目录, 默认 data/recon/raw_poll
  --verbose          打印每只持仓行

依赖: requests, 项目根 src/storage/sqlite_storage.py
"""
import argparse
import json
import sqlite3
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import requests

PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

from src.storage.sqlite_storage import SQLiteStorage  # noqa: E402

# -------
# API 常量
# -------
API_BASE = "https://emdcspzhapi.eastmoney.com/rtV2"
EM_HEADERS_FILE = PROJ_ROOT / "config" / "em_headers.json"

RECON_DIR = PROJ_ROOT / "data" / "recon" / "raw_poll"
RECON_DIR.mkdir(parents=True, exist_ok=True)


# -------
# 加载 EM-* 设备鉴权头 (token 时效短, 失效后 Edit config/em_headers.json)
# -------
_STATIC_HEADERS = {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=UTF-8",
    "EM-CHL": "taobao45",
    "EM-CT": "",
    "EM-OS": "Android",
    "EM-PA": "1",
    "EM-SL": "0",
    "EM-UT": "",
    "User-Agent": "okhttp/3.12.13",
    "Host": "emdcspzhapi.eastmoney.com",
}

_DYNAMIC_EM_KEYS = ("EM-MD", "EM-GT", "EM-GV", "EM-VER", "EM-PKG")
_EM_HEADERS_MTIME: float = 0.0
_EM_HEADERS_CACHE: dict = {}


def load_em_headers() -> dict:
    """从 config/em_headers.json 读取并刷新缓存的 EM 鉴权头。
    每次调用重读 mtime,无需重启 web 即可不 reload 文件。"""
    global _EM_HEADERS_MTIME, _EM_HEADERS_CACHE
    if EM_HEADERS_FILE.exists():
        m = EM_HEADERS_FILE.stat().st_mtime
        if m != _EM_HEADERS_MTIME:
            _EM_HEADERS_MTIME = m
            _EM_HEADERS_CACHE = json.loads(EM_HEADERS_FILE.read_text(encoding="utf-8"))
    cfg = _EM_HEADERS_CACHE or {}
    h = dict(_STATIC_HEADERS)
    for k in _DYNAMIC_EM_KEYS:
        v = cfg.get(k)
        if v:
            h[k] = v
    return h


# -------
# API 调用
# -------
def _safe_float(v) -> float:
    """容错转换: +∞ / -∞ / NaN / 科学计数 / 空 / '-' / 含中文 -> 0.0"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ("-", "--", "—"):
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _post_detail(zh_id: str) -> dict:
    """POST emdcspzhapi.eastmoney.com/rtV2 method=combination_detail_97"""
    headers = load_em_headers()
    body = {
        "args": {"reqUserid": "", "zh": zh_id},
        "clientType": "cfzq",
        "method": "combination_detail_97",
        "client": "android",
        "appKey": "eastmoney",
        "clientVersion": "10.13.5",
        "randomCode": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
    }
    r = requests.post(API_BASE, json=body, headers=headers, timeout=15)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(f"API error zh={zh_id} method=combination_detail_97: {j.get('message')}; raw={r.text[:300]}")
    return j["data"]


# -------
# 选手详情 -> players 行
# -------
def map_player(zh_id: str, d: dict | None) -> dict:
    """从 combination_detail_97 返回的 detail 子键映射到 SQLiteStorage.players schema."""
    d = d or {}
    # label 字段是数组,我们将 labels 字段简化存为 JSON 数组
    return {
        "zh_id": zh_id,
        "name": d.get("zuheName") or d.get("uidNick") or "",
        "followers": int(_safe_float(d.get("concernCnt"))),
        "total_return": _safe_float(d.get("rate")),
        "daily_return": _safe_float(d.get("rateDay")),
        "net_value": _safe_float(d.get("JZ")),
        "max_drawdown": _safe_float(d.get("maxDrawDown")),
        "win_rate": _safe_float(d.get("dealRate")),
        "days": int(_safe_float(d.get("yxts"))),
        "concept": d.get("vType", "") or "",
        "intro": d.get("comment", "") or d.get("uidComment", "") or "",
        "user_id": d.get("userid", "") or "",
        "labels": [],
        "ranks": [],
    }


# -------
# 持仓 -> list[dict]
# -------
def map_positions(zh_id: str, rows: list | None) -> list[dict]:
    out = []
    for row in rows or []:
        out.append({
            "zh_id": zh_id,
            "stock_code": str(row.get("__code") or ""),
            "stock_name": row.get("__name") or "",
            "cost_price": _safe_float(row.get("cbj")),
            "current_price": _safe_float(row.get("__zxjg")),
            "profit_ratio": _safe_float(row.get("webYkRate")),
            "position_ratio": _safe_float(row.get("holdPos") or row.get("positionRateDetail")),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "_stk_mkt_code": row.get("stkMktCode", ""),
            "_fullcode": row.get("fullcode", ""),
        })
    return out


# -------
# 调仓 -> list[dict]
# -------
def map_trades(zh_id: str, rows: list | None) -> list[dict]:
    out = []
    for row in rows or []:
        mkt = row.get("stkMktCode", "") or ""
        code = mkt[2:] if mkt[:2] in ("SH", "SZ", "BJ") else mkt
        common = {
            "zh_id": zh_id,
            "stock_code": code,
            "stock_name": row.get("stkName", "") or "",
            "trade_date": row.get("tzrq", "") or "",
            "stk_mkt_code": mkt,
            "stock_fullcode": row.get("fullcode", "") or "",
        }
        mr = int(_safe_float(row.get("lshj_mr")))
        if mr > 0:
            out.append({**common,
                         "direction": "buy",
                         "qty": mr,
                         "qty_str": row.get("lshj_mr"),
                         "price": _safe_float(row.get("cjjg_mr")),
                         "position_ratio_str": row.get("cwhj_mr", "") or "--",
                         "raw": row})
        mc = int(_safe_float(row.get("lshj_mc")))
        if mc > 0:
            out.append({**common,
                         "direction": "sell",
                         "qty": mc,
                         "qty_str": row.get("lshj_mc"),
                         "price": _safe_float(row.get("cjjg_mc")),
                         "position_ratio_str": row.get("cwhj_mc", "") or "--",
                         "raw": row})
        if mr == 0 and mc == 0:
            out.append({**common,
                         "direction": "noop",
                         "qty": 0,
                         "qty_str": "0",
                         "price": 0.0,
                         "position_ratio_str": "--",
                         "raw": row})
    return out


# -------
# zhid 列表
# -------
def load_zhids(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


# -------
# 玩家最小 upsert (持仓/调仓 FK 需要 players 行)
# -------
def ensure_player(storage: SQLiteStorage, zh_id: str) -> None:
    if not storage.exists(zh_id):
        storage.save_player({"zh_id": zh_id, "name": ""})


# -------
# 告警: 用 (zh_id, stock_code, trade_date, direction, qty) 复合 key 同 DB 去 diff
# -------
def _existing_trade_keys(conn: sqlite3.Connection, zh_id: str, crawl_date: str) -> set[tuple]:
    rows = conn.execute(
        "SELECT stock_code, trade_date, direction, position_change"
        "  FROM trades WHERE zh_id=? AND crawl_date=?",
        (zh_id, crawl_date)
    ).fetchall()
    return {(r[0], r[1], r[2], r[3]) for r in rows}


def emit_alert(alerts_log: Path, zh_id: str, t: dict) -> None:
    line = (f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"NEW TRADE zh={zh_id} {t['direction']} {t.get('stock_name','')}"
            f" code={t.get('stock_code','')} qty={t.get('qty',0)} "
            f"price={t.get('price',0)} date={t.get('trade_date','')} "
            f"pos={t.get('position_ratio_str','')}")
    with alerts_log.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print("  " + line)


# -------
# 单选手一轮 — 一次 POST combination_detail_97 拿全 detail/positions/trades
# -------
def poll_one(storage: SQLiteStorage, zh_id: str, *,
             crawl_date: str, alerts_log: Path, verbose: bool = False) -> dict:
    # 1) 一次 API 调用拿全
    try:
        payload = _post_detail(zh_id)
    except Exception as e:
        print(f"[{zh_id}] DETAIL FAIL: {e}")
        return {"zh_id": zh_id, "ok": False, "err": str(e)}

    # 原始存档
    try:
        (RECON_DIR / f"detail_{zh_id}_{crawl_date}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    # 2) 选手详情 -> players
    player = map_player(zh_id, payload.get("detail"))
    storage.save_player(player)
    print(f"[{zh_id}] {player['name']}  total={player['total_return']}% day={player['daily_return']}% dd={player['max_drawdown']}%")

    positions = map_positions(zh_id, payload.get("position"))
    storage.save_positions(zh_id, positions, crawl_date=crawl_date)
    print(f"[{zh_id}] holdings: {len(positions)} rows @ {crawl_date}")
    if verbose:
        for p in positions:
            print(f"     {p['stock_code']:>8} {p['stock_name']:<14} pos={p['position_ratio']:>5.2f}% yk={p['profit_ratio']:>6.2f}% cost={p['cost_price']:<8} now={p['current_price']}")

    trades = map_trades(zh_id, payload.get("tradeSummary"))

    # 3) diff: 在 truncate 当日 trades 前先抽现有 key 做差异对比
    with storage.get_connection() as conn:
        existing = _existing_trade_keys(conn, zh_id, crawl_date)
        new_trades = [t for t in trades
                     if (t.get("stock_code",""), t.get("trade_date",""),
                         t.get("direction",""), int(t.get("qty",0)))
                     not in existing]
        for t in new_trades:
            if t.get("direction") in ("buy", "sell"):
                emit_alert(alerts_log, zh_id, t)

    # 4) 写入
    trade_rows = [{
        "stock_code": t.get("stock_code", ""),
        "stock_name": t.get("stock_name", ""),
        "trade_date": t.get("trade_date", ""),
        "direction": t.get("direction", ""),
        "position_change": float(t.get("qty", 0) or 0),
        "position_ratio": t.get("position_ratio_str", "") or "",
        "position_value": float(t.get("price", 0) or 0),
        "trades_count": 1,
    } for t in trades if t.get("direction") in ("buy", "sell")]
    storage.save_trades(zh_id, trade_rows, crawl_date=crawl_date)
    n_new = len([t for t in new_trades if t.get("direction") in ("buy","sell")])
    print(f"[{zh_id}] trades: {len(trade_rows)} rows; new alerts: {n_new}")
    return {"zh_id": zh_id, "ok": True,
            "name": player["name"],
            "n_pos": len(positions), "n_trades": len(trade_rows), "new_alerts": n_new}


# -------
# 主循环
# -------
def poll_round(zhids: list[str], storage: SQLiteStorage, alerts_log: Path,
               verbose: bool = False) -> list[dict]:
    crawl_date = date.today().isoformat()
    print(f"\n=== poll round {datetime.now().isoformat(timespec='seconds')} crawl_date={crawl_date} n={len(zhids)} ===")
    results = []
    for zh in zhids:
        try:
            r = poll_one(storage, zh, crawl_date=crawl_date,
                         alerts_log=alerts_log, verbose=verbose)
        except Exception as e:
            print(f"[{zh}] unexpected: {e}")
            r = {"zh_id": zh, "ok": False, "err": str(e)}
        results.append(r)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="持续轮询")
    ap.add_argument("--interval", type=int, default=300, help="轮询间隔秒, 默认 300")
    ap.add_argument("--zhids", type=Path, default=PROJ_ROOT / "config" / "zhids.txt")
    ap.add_argument("--db", type=Path, default=PROJ_ROOT / "data" / "crawl_data.db")
    ap.add_argument("--alerts", type=Path, default=PROJ_ROOT / "data" / "alerts.log")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    storage = SQLiteStorage(args.db)
    alerts_log = args.alerts
    alerts_log.parent.mkdir(parents=True, exist_ok=True)
    zhids = load_zhids(args.zhids)
    if not zhids:
        print(f"no zhids to poll (check {args.zhids})")
        return

    if not args.loop:
        poll_round(zhids, storage, alerts_log, args.verbose)
        return

    print(f"polling loop: {len(zhids)} zhids, interval {args.interval}s — Ctrl+C to stop")
    round_n = 0
    try:
        while True:
            round_n += 1
            poll_round(zhids, storage, alerts_log, args.verbose)
            print(f"--- round {round_n} done, sleeping {args.interval}s ---")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()