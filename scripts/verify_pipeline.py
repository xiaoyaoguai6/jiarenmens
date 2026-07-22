"""
verify_pipeline.py  --  End-to-end verification of scraper -> SQLite -> trade-diff
on REAL captured flow data.

Strategy:
1) Extract zhid=900296556 CombinationHoldPositionPermitHandler request+response
   from data/recon/em_first_session.flows (the user's earlier voluntary clicks
   while berlin APP was running). The response is the schema containing sector
   bucket + stock rows, fully matching what mitm_em_position_extractor expects.
2) Synthesize a positions.jsonl event for it (same structure the addon would
   produce), feed into storage_bridge.drain_once, and verify the SQLite
   positions table now has rows for zhid=900296556 with the right stock code.
3) Synthesize a SECOND event with an extra "(stock_code=600105 direction=sell
   qty=3700 date=20260710)" trade to simulate a fresh scrape that picks up a
   new trade. Verify the poller's diff_one() reports this as a new trade and
   the alert log captures it.

This avoids the need for an interactive LDPlayer / live mitm session to
complete the end-to-end verification.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from mitm_em_position_extractor import (
    parse_request_body, extract_positions, extract_trades,
)
from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger

logger = setup_logger()

RECON_DIR = ROOT / "data" / "recon"
EVENTS_FILE = RECON_DIR / "positions.jsonl"
FLOW_FILE = RECON_DIR / "em_first_session.flows"
TEST_DB = RECON_DIR / "verify_test.db"


def capture_block(fpath: Path, host: str = "spzhapi.dfcfs.cn",
                  method_target: str = "CombinationHoldPositionPermitHandler",
                  zhid_target: str = "900296556") -> dict | None:
    """Walk flow file; for the first rtV3 request whose body method matches,
    capture it; pair with the next response (in flow sequence).
    """
    events = []
    for line in fpath.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("host") != host:
            continue
        events.append(rec)

    requests = [e for e in events if e.get("phase") == "request"]
    responses = [e for e in events if e.get("phase") == "response"]

    n = min(len(requests), len(responses))
    for i in range(n):
        req = requests[i]
        body = req.get("body", "")
        parsed = parse_request_body(body)
        if parsed.get("method") != method_target:
            continue
        if parsed.get("zh_id") != zhid_target:
            continue
        resp = responses[i]
        # Reconstitute JSON from body_preview
        try:
            resp_json = json.loads(resp["body_preview"])
        except Exception as e:
            logger.warning(f"failed parse response body_preview: {e}")
            continue
        return {"request": req, "response": resp, "parsed": parsed, "resp_json": resp_json}
    return None


def append_event(ev: dict):
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")


def reset_files():
    if EVENTS_FILE.exists():
        EVENTS_FILE.unlink()
    if (RECON_DIR / "storage_bridge.offset").exists():
        (RECON_DIR / "storage_bridge.offset").unlink()
    if TEST_DB.exists():
        TEST_DB.unlink()
    if (RECON_DIR / "poller_state.json").exists():
        (RECON_DIR / "poller_state.json").unlink()
    if (RECON_DIR / "alerts.log").exists():
        (RECON_DIR / "alerts.log").unlink()


def main():
    reset_files()

    # ----- step 1: pull a real HoldPosition response from the captures
    cap = capture_block(FLOW_FILE, method_target="CombinationHoldPositionPermitHandler",
                        zhid_target="900296556")
    if cap is None:
        print("[FAIL] could not find matching capture for zhid=900296556 HoldPositionPermitHandler")
        return 1
    print(f"[OK] matched capture: zhid={cap['parsed']['zh_id']} method={cap['parsed']['method']}")
    print(f"     response code={cap['resp_json'].get('code')} msg={cap['resp_json'].get('message')}")

    positions = extract_positions(cap['resp_json'], "900296556")
    if not positions:
        print("[FAIL] extract_positions returned empty list")
        return 1
    print(f"[OK] extracted {len(positions)} position row(s)")
    for p in positions:
        kv = {k: p[k] for k in p if k != "raw"}
        print(f"     - {kv}")

    # ----- step 2: synthesize event and push to storage_bridge
    event1 = {
        "ts": time.time(),
        "kind": "position",
        "zh_id": "900296556",
        "method": "CombinationHoldPositionPermitHandler",
        "code": 0,
        "message": "Success",
        "data": positions,
    }
    append_event(event1)

    storage1 = get_storage()
    # Configure storage to use TEST_DB
    storage1.db_path = TEST_DB
    storage1._init_db()

    from storage_bridge import drain_once
    r = drain_once(storage1)
    print(f"[OK] drain_once: {r['processed']} processed, {r['skipped']} skipped")
    if r['errors']:
        print(f"[WARN] errors: {r['errors']}")

    # Verify SQLite positions table
    conn = sqlite3.connect(TEST_DB)
    rows = conn.execute(
        "SELECT zh_id, stock_code, stock_name, cost_price, current_price, profit_ratio, position_ratio "
        "FROM positions WHERE zh_id=?",
        ("900296556",),
    ).fetchall()
    print(f"[OK] sqlite has {len(rows)} position row(s) for zhid=900296556")
    if not rows:
        print("[FAIL] No positions written to database")
        return 1
    for row in rows[:3]:
        print(f"     - {row}")

    # Also save a corresponding trade event
    synthesize_trade_event = {
        "ts": time.time() + 0.1,
        "kind": "trade",
        "zh_id": "900296556",
        "method": "CombinationRelocatePositionHandler",
        "code": 0,
        "message": "Success",
        "data": {
            "kind": "trade_list",
            "total_pages": 1,
            "page_index": 1,
            "total_count": 1,
            "trades": [{
                "zh_id": "900296556",
                "stock_code": "600105",
                "stock_name": "永鼎股份",
                "market": "1",
                "trade_date": "20260710",
                "relocateTime": "2026-07-10 15:00:00",
                "direction": "sell",
                "qty": 3700,
                "price": 49.04,
                "position_ratio": "1成以",
                "raw": {"bsMark": "S", "relocateQty": 3700},
            }]
        }
    }
    append_event(synthesize_trade_event)
    r = drain_once(storage1)
    print(f"[OK] trade drain: {r['processed']} processed, {r['skipped']} skipped")
    trade_rows = conn.execute(
        "SELECT zh_id, stock_code, stock_name, direction, trade_date, position_change "
        "FROM trades WHERE zh_id=?",
        ("900296556",),
    ).fetchall()
    print(f"[OK] sqlite has {len(trade_rows)} trade row(s) for zhid=900296556")
    for row in trade_rows[:3]:
        print(f"     - {row}")
    if not trade_rows:
        print("[FAIL] No trades in DB")
        return 1

    # ----- step 3: simulate the poller's diff_one() with this current state vs empty state
    sys.path.insert(0, str(ROOT / "scripts"))
    from scraper_poller import diff_one, save_state, load_state, append_alert, trade_signature
    prev_state = {"900296556": {"trades": {}}}
    new_rows, current_sigs = diff_one("900296556", prev_state["900296556"]["trades"])
    print(f"[OK] diff_one: {len(new_rows)} new trade(s)")
    if len(new_rows) != 1:
        print(f"[FAIL] expected 1 new trade, got {len(new_rows)}")
        return 1
    for r in new_rows:
        print(f"     new trade: {r}")
        append_alert(f"NEW TRADE zh=900296556 {r['direction']} {r['stock_code']} "
                      f"qty={r['position_change']} date={r['trade_date']}")

    saved_state = {"900296556": {"trades": current_sigs}}
    save_state(saved_state)

    # ----- step 4: simulate SECOND round where additional trade detected
    # Append an additional trade event with different signature (qty doubled)
    synthesize_trade_event2 = {
        "ts": time.time() + 0.5,
        "kind": "trade",
        "zh_id": "900296556",
        "method": "CombinationRelocatePositionHandler",
        "code": 0,
        "message": "Success",
        "data": {
            "kind": "trade_list",
            "total_pages": 1, "page_index": 1, "total_count": 2,
            "trades": [
                synthesize_trade_event["data"]["trades"][0],
                {
                    "zh_id": "900296556",
                    "stock_code": "600105",
                    "stock_name": "永鼎股份",
                    "market": "1",
                    "trade_date": "20260710",
                    "relocateTime": "2026-07-10 16:30:00",
                    "direction": "buy",
                    "qty": 2000,
                    "price": 49.20,
                    "position_ratio": "1成以",
                    "raw": {"bsMark": "B", "relocateQty": 2000},
                }
            ]
        }
    }
    append_event(synthesize_trade_event2)
    r = drain_once(storage1)
    print(f"[OK] round-2 drain: {r['processed']} processed")

    # Now diff against the previous state
    # IMPORTANT: load recent trades for today and compare
    new_rows2, current_sigs2 = diff_one("900296556", saved_state["900296556"]["trades"])
    print(f"[OK] round-2 diff: {len(new_rows2)} new trade(s)")
    if len(new_rows2) != 1:
        print(f"[FAIL] expected 1 NEW trade in round 2, got {len(new_rows2)}")
        return 1
    for r in new_rows2:
        print(f"     new trade: {r}")
        append_alert(f"NEW TRADE zh=900296556 {r['direction']} {r['stock_code']} "
                      f"qty={r['position_change']} date={r['trade_date']}")
    print()
    print("[END-TO-END] All checks passed!")
    print("Final artifacts:")
    print(f"  - positions in SQLite:        {len(rows)}")
    print(f"  - trades in SQLite:          {len(trade_rows)}")
    print(f"  - alerts emitted:            >>> see data/recon/alerts.log")
    print(f"  - poller state persisted at:  data/recon/poller_state.json")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)