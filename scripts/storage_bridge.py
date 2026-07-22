"""
storage_bridge.py  --  Consume mitm SmartInterceptor events (positions.jsonl)
and upsert into SQLite (existing schema in src/storage/sqlite_storage.py).

Each event in positions.jsonl is one JSON line:
    {
      "ts": <float>,
      "kind": "position" | "trade" | "block",
      "zh_id": "900296556",
      "method": "CombinationHoldPositionPermitHandler",
      "code": 0,                       # server response code
      "message": "Success",
      "data":
        [                               # for "position" kind: list of row dicts
          {"zh_id","stock_code","stock_name","sector","cost_price",
           "current_price","profit_ratio","position_ratio","raw"}
        ]
        OR for "trade":
        { "kind":"trade_list","total_pages","page_index","total_count",
          "trades":[{"zh_id","stock_code","stock_name","market","trade_date",
                    "direction":"buy|sell","qty","price","position_ratio","raw"}] }
    }

If multiple events for the same zh_id arrive on the same crawl_date, only the
latest set of positions / trades is kept (save_positions/trades use
DELETE-then-INSERT semantics).

CLI usage:
    python scripts/storage_bridge.py                    # one-shot drain
    python scripts/storage_bridge.py --watch            # tail -F style
"""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

# Allow `python scripts/storage_bridge.py` direct invocation
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger

logger = setup_logger()

RECON_DIR = ROOT / "data" / "recon"
EVENTS_PATH = RECON_DIR / "positions.jsonl"

# Offsets we increment through; positions.jsonl is append-only by mitm addon,
# so storage_bridge reads up to its own last-seen line offset and remembers it.
OFFSET_FILE = RECON_DIR / "storage_bridge.offset"


def _read_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip() or "0")
        except Exception:
            return 0
    return 0


def _save_offset(n: int) -> None:
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(n))


def _normalize_position_row(zh_id: str, row: dict) -> dict:
    raw = row.get("raw", {}) if isinstance(row, dict) else {}
    cost = row.get("cost_price") or float(raw.get("cbj", 0) or 0)
    cur = row.get("current_price") or float(raw.get("__zxjg", 0) or
                                              raw.get("zxjg", 0) or 0)
    return {
        "stock_code": row.get("stock_code") or raw.get("__code") or "",
        "stock_name": row.get("stock_name") or raw.get("__name") or "",
        "cost_price": cost,
        "current_price": cur,
        "profit_ratio": float(row.get("profit_ratio") or
                              raw.get("webYkRate", 0) or 0),
        "position_ratio": float(row.get("position_ratio") or
                                  raw.get("holdPos") or
                                  raw.get("positionRateDetail") or 0),
        "update_time": "",
    }


def _normalize_trade_row(zh_id: str, row: dict) -> dict:
    raw = row.get("raw", {}) if isinstance(row, dict) else {}
    return {
        "stock_code": row.get("stock_code") or raw.get("stkCode", ""),
        "stock_name": row.get("stock_name") or raw.get("stkName", ""),
        "direction": row.get("direction") or
            ("buy" if raw.get("bsMark") == "B" else
             "sell" if raw.get("bsMark") == "S" else
             str(raw.get("bsMark", ""))),
        "trade_date": row.get("trade_date") or str(raw.get("bizDate", "")),
        "position_ratio": row.get("position_ratio") or
            raw.get("positionRatio", ""),
        "position_change": float(row.get("qty") or raw.get("relocateQty", 0) or 0),
        "position_value": float(row.get("price") or raw.get("relocatePrice", 0) or 0),
        "trades_count": 1,
    }


def _process_event(ev: dict, storage) -> dict:
    """Upsert one event into SQLite; returns short summary dict."""
    kind = ev.get("kind")
    zh_id = ev.get("zh_id")
    if not zh_id:
        return {"skipped": "no zh_id"}
    crawl_date = date.today().isoformat()

    if kind == "position":
        data = ev.get("data")
        if not isinstance(data, list):
            return {"skipped": "position data not list"}
        positions = [_normalize_position_row(zh_id, r) for r in data]
        storage.save_positions(zh_id, positions, crawl_date=crawl_date)
        return {"kind": "position", "zh_id": zh_id, "n": len(positions)}

    if kind == "trade":
        data = ev.get("data", {})
        if not isinstance(data, dict):
            return {"skipped": "trade data not dict"}
        trades_raw = data.get("trades", []) or []
        trades = [_normalize_trade_row(zh_id, r) for r in trades_raw]
        storage.save_trades(zh_id, trades, crawl_date=crawl_date)
        return {"kind": "trade", "zh_id": zh_id, "n": len(trades)}

    # block events are informational only (sector breakdown)
    return {"skipped": f"kind={kind} ignored"}


def drain_once(storage, stop_after_first_error: bool = False) -> dict:
    """Read events past the last offset and upsert each one into storage.

    Returns a summary dict.
    """
    if not EVENTS_PATH.exists():
        return {"processed": 0, "error": "no events file yet"}

    offset = _read_offset()
    log_size = EVENTS_PATH.stat().st_size
    if offset > log_size:
        # file was truncated/rotated -- start over
        offset = 0

    processed = 0
    skipped = 0
    errors = []
    summaries = []

    # Read line-by-line from offset to log_size without loading whole file.
    with EVENTS_PATH.open("r", encoding="utf-8") as f:
        f.seek(offset)
        while True:
            line = f.readline()
            if not line:
                break
            offset = f.tell()
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except Exception as e:
                errors.append(f"json: {e}")
                if stop_after_first_error:
                    break
                continue
            try:
                summary = _process_event(ev, storage)
                summaries.append(summary)
                if "skipped" in summary:
                    skipped += 1
                else:
                    processed += 1
            except Exception as e:
                errors.append(f"upsert: {e}")
                if stop_after_first_error:
                    break
                continue
            _save_offset(offset)
    _save_offset(offset)
    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "summaries": summaries,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true",
                        help="Tail -F positions.jsonl, flush every 1s")
    parser.add_argument("--reset", action="store_true",
                        help="Reset stored offset to 0 and absorb all events")
    args = parser.parse_args()

    if args.reset:
        _save_offset(0)
        logger.info("offset reset to 0")

    storage = get_storage()

    if args.watch:
        logger.info("storage_bridge running in watch mode (Ctrl-C to stop)")
        while True:
            r = drain_once(storage)
            if r["processed"] or r.get("errors"):
                logger.info(f"storage_bridge: {r['processed']} processed, "
                            f"{r['skipped']} skipped, {len(r.get('errors', []))} errors")
                for s in r.get("summaries", []):
                    print(s, flush=True)
                for e in r.get("errors", [])[:5]:
                    logger.warning(f"err: {e}")
            time.sleep(1)
    else:
        r = drain_once(storage)
        logger.info(f"storage_bridge: {r['processed']} processed, "
                    f"{r['skipped']} skipped, "
                    f"{len(r.get('errors', []))} errors")
        for s in r.get("summaries", []):
            print(s, flush=True)
        for e in r.get("errors", [])[:10]:
            logger.warning(f"err: {e}")


if __name__ == "__main__":
    main()