"""
scraper_poller.py  --  Main poller loop.

Combines:
  * em_scraper_driver.scrape_one_player(zh_id)   drives the LDPlayer UI
    so the EM APP issues CombinationHoldPositionPermitHandler + Relocate
    requests, which mitm captures via the SmartInterceptor addon.
  * storage_bridge.drain_once(storage)            upserts events per zh_id
    into SQLite (positions/trades tables by crawl_date).
  * diff vs last-round snapshot of `trades` -- alert on any new trade
    line that did not exist on the previous round (keyed by zh_id +
    stock_code + trade_date + direction).

Usage:
    python scripts/scraper_poller.py --zhids 900083077,900296556
    python scripts/scraper_poller.py --zhids-file config/zhids.txt --interval 300
"""
import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Set, List, Dict, Tuple

# import paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from em_scraper_driver import scrape_one_player, ensure_app_alive
from storage_bridge import drain_once, _save_offset
from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger

logger = setup_logger()

STATE_PATH = ROOT / "data" / "recon" / "poller_state.json"
ALERT_LOG_PATH = ROOT / "data" / "recon" / "alerts.log"


# ---------------- Diff Tracker --------------------------------------------------

def load_state() -> Dict[str, dict]:
    """Read last seen trade-signatures per zh_id. Returns {zh_id: {trade_key: row_metadata}}"""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: Dict[str, dict]):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def trade_signature(row: dict) -> str:
    """Single-string signature -- used to diff against last round."""
    return "|".join([
        str(row.get("trade_date", "")),
        str(row.get("stock_code", "")),
        str(row.get("direction", "")),
        str(row.get("position_change", 0)),
    ])


def load_recent_trades(zh_id: str) -> List[dict]:
    storage = get_storage()
    rows = storage.load_trades(zh_id, crawl_date=date.today().isoformat())
    return rows


def diff_one(zh_id: str, prev_zh_state: dict) -> List[dict]:
    """Compare last seen trades to current; return new rows added."""
    current_rows = load_recent_trades(zh_id)
    current_sigs = {trade_signature(r): r for r in current_rows}
    new_rows = []
    for sig, row in current_sigs.items():
        if sig not in prev_zh_state:
            new_rows.append(row)
    return new_rows, current_sigs


def append_alert(msg: str):
    ALERT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    logger.info("ALERT: " + msg)


# ---------------- Main poller loop ----------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--zhids", type=str, default="",
                   help="comma-separated list of zh_ids (overrides --zhids-file)")
    p.add_argument("--zhids-file", type=str,
                   default=str(ROOT / "config" / "zhids.txt"),
                   help="newline/comma-separated file of zh_ids")
    p.add_argument("--interval", type=int, default=300,
                   help="pause between rounds, in seconds (default 300 = 5 min)")
    p.add_argument("--rounds", type=int, default=0,
                   help="how many rounds to run; 0 = forever")
    p.add_argument("--hold-only", action="store_true",
                   help="skip 调仓 tab (only 持仓 for")
    args = p.parse_args()
    return args


def read_zhids_file(path: str) -> List[str]:
    p = Path(path)
    if not p.exists():
        return []
    out: List[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip().strip(",")
        if not line or line.startswith("#"):
            continue
        for tok in line.split(","):
            tok = tok.strip()
            if tok:
                out.append(tok)
    return out


def main():
    args = parse_args()

    if args.zhids:
        zh_ids: List[str] = [z.strip() for z in args.zhids.split(",") if z.strip()]
    else:
        zh_ids = read_zhids_file(args.zhids_file)
    if not zh_ids:
        logger.error("No zh_ids provided. Use --zhids or write config/zhids.txt.")
        sys.exit(2)

    logger.info(f"poller starting with {len(zh_ids)} zh_ids: {zh_ids}")
    logger.info(f"interval = {args.interval}s")

    # sanity-check LDPlayer + EM APP alive
    if not ensure_app_alive():
        logger.error("EM APP cannot be started; aborting. Check LDPlayer connectivity.")
        sys.exit(3)

    state = load_state()
    rounds = 0
    while True:
        rounds += 1
        logger.info(f"=== round #{rounds} ({date.today().isoformat()}) ===")

        # Reset storage_bridge offset to absorb only fresh events from THIS round
        _save_offset(0)

        per_round_capture = {}
        for zh in zh_ids:
            logger.info(f"scraping {zh}")
            r = scrape_one_player(zh, hold=True, trade=not args.hold_only)
            logger.info(f"  -> {r}")
            time.sleep(1.5)

        # Absorb whatever mitm captured into SQLite
        storage = get_storage()
        drain = drain_once(storage)
        logger.info(f"storage drained: {drain['processed']} processed, "
                    f"{drain['skipped']} skipped")

        # Diff trades vs last round; alert on new ones
        for zh in zh_ids:
            prev = state.setdefault(zh, {"trades": {}})
            new_rows, sign_map = diff_one(zh, prev.get("trades", {}))
            if new_rows:
                logger.info(f"  {zh}: {len(new_rows)} new trade(s) detected")
                for r in new_rows:
                    append_alert(f"NEW TRADE zh={zh} {r.get('direction')} "
                                  f"{r.get('stock_code')} ({r.get('stock_name','')}) "
                                  f"qty={r.get('position_change')} "
                                  f"date={r.get('trade_date')}")
            # update prev state with current sig map
            prev["trades"] = sign_map
        save_state(state)

        if args.rounds and rounds >= args.rounds:
            logger.info("round limit reached, exiting")
            break

        logger.info(f"sleeping {args.interval}s before next round")
        # But first, do one drain before sleeping, just in case mitm has any extra
        # events trickling in
        time.sleep(min(5, args.interval))
        drain = drain_once(get_storage())
        if drain["processed"]:
            logger.info(f"post-scrape drain: {drain['processed']} more events")
        sleep_remaining = max(0, args.interval - 5)
        time.sleep(sleep_remaining)


if __name__ == "__main__":
    main()