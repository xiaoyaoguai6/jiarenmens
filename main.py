"""
DongFangCaiFu ShiPan Player Crawler (API-only mode)

Pure API crawler using the rt_get_rank leaderboard endpoint.
Returns per-player return rates across 5 time periods (total,
250-day, 20-day, 5-day, daily).

All individual detail APIs (rt_get_info, rt_get_position, etc.)
return -10000 server-side rejection, so we enrich player profiles
using rank data from all 5 time periods.
"""
import json
import sys
from pathlib import Path
from datetime import date
from typing import List, Dict, Any

from src.spiders.player_list import PlayerListSpider
from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger

logger = setup_logger()

CHECKPOINT_FILE = Path(__file__).parent / "data" / "checkpoint.json"


# ---------------------------------------------------------------------------
# Checkpoint helpers (kept for backwards compatibility with old runs)
# ---------------------------------------------------------------------------

def load_checkpoint() -> Dict[str, Any]:
    if not CHECKPOINT_FILE.exists():
        return {"last_index": 0, "completed_ids": [], "last_list_update": None, "start_time": None}
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load checkpoint: {e}")
        return {"last_index": 0, "completed_ids": [], "last_list_update": None, "start_time": None}


def save_checkpoint(state: Dict[str, Any]):
    try:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINT_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
        tmp.replace(CHECKPOINT_FILE)
    except Exception as e:
        logger.warning(f"Failed to save checkpoint: {e}")


# ---------------------------------------------------------------------------
# Convert rank-enriched player dict to DB-ready dict
# ---------------------------------------------------------------------------

def player_to_db_row(p: Dict[str, Any]) -> Dict[str, Any]:
    """Map the enriched player dict from PlayerListSpider to the players table schema."""
    return {
        "zh_id": p.get("zh_id"),
        "name": p.get("name", ""),
        "followers": p.get("followers", 0),
        "total_return": p.get("return_total") or 0.0,
        "daily_return": p.get("return_daily") or 0.0,
        "net_value": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "days": 0,
        "concept": "",
        "intro": "",
        "user_id": p.get("user_id", ""),
        "labels": p.get("labels", []),
        "ranks": {rk: {"return": p.get(fk)} for (_rt, (rk, fk)) in
                   [("10004", ("总榜", "return_total")),
                    ("10003", ("年榜", "return_250d")),
                    ("10001", ("月榜", "return_20d")),
                    ("10000", ("周榜", "return_5d")),
                    ("10005", ("日榜", "return_daily"))]
                   if p.get(fk) is not None},
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    # --analyze pass-through
    if "--analyze" in sys.argv:
        from src.analysis.position_analyzer import analyze_positions
        sys.argv = [a for a in sys.argv if a != "--analyze"]
        analyze_positions()
        return

    parser = argparse.ArgumentParser(description="DongFangCaiFu ShiPan Player Crawler (API-only)")
    parser.add_argument("--test", action="store_true", help="Test mode (first 10 players only)")
    parser.add_argument("--limit", type=int, default=500, help="Players per rank (default: 500)")
    parser.add_argument("--workers", type=int, default=20, help="[IGNORED - kept for compat]")
    parser.add_argument("--no-skip", action="store_true", help="[IGNORED - kept for compat]")
    parser.add_argument("--checkpoint-reset", action="store_true", help="Reset checkpoint")
    args = parser.parse_args()

    if args.checkpoint_reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("Checkpoint reset")

    storage = get_storage()

    logger.info("=" * 60)
    logger.info("DongFangCaiFu ShiPan Player Crawler (API-only)")
    logger.info(f"Limit per rank: {args.limit}")
    logger.info(f"Storage: SQLite")
    logger.info("=" * 60)

    # Step 1: fetch enriched player list from the rank API
    logger.info("\n[Step 1] Fetching player list (enriched with multi-period returns)...")
    spider = PlayerListSpider()
    players = spider.fetch_player_list(max_per_rank=args.limit)

    if not players:
        logger.warning("No players fetched")
        return

    if args.test:
        players = players[:10]
        logger.info(f"Test mode: processing first {len(players)} players only")

    logger.info(f"Total unique players: {len(players)}")

    # Step 2: save directly to DB (no browser scraping needed)
    logger.info("\n[Step 2] Saving enriched player data to SQLite...")
    crawl_date = date.today().isoformat()

    db_rows = [player_to_db_row(p) for p in players]
    storage.save_players_batch(db_rows)

    logger.info(f"Saved {len(db_rows)} player records")

    # Print a quick summary
    with_total = sum(1 for p in players if p.get("return_total") is not None)
    with_daily = sum(1 for p in players if p.get("return_daily") is not None)
    logger.info(f"  Players with total return data: {with_total}/{len(players)}")
    logger.info(f"  Players with daily return data: {with_daily}/{len(players)}")
    logger.info(f"  Crawl date: {crawl_date}")
    logger.info("\nDone!")


if __name__ == "__main__":
    main()
