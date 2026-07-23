"""
每日榜单数据抓取
================
全量抓取东方财富 5 种收益榜单选手数据，更新到 DB。
建议通过 Windows 任务计划程序每天定时运行一次。

用法:
    python scripts/daily_fetch.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.spiders.player_list import PlayerListSpider
from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger

logger = setup_logger()


def main():
    logger.info("=" * 60)
    logger.info("每日榜单数据抓取 - 开始")
    logger.info("=" * 60)

    # Step 1: 从 5 个榜单 API 获取选手数据
    logger.info("正在从 5 个收益榜单获取选手数据...")
    spider = PlayerListSpider()
    players = spider.fetch_player_list(max_per_rank=500)

    if not players:
        logger.error("未获取到任何选手数据，终止")
        return

    logger.info(f"去重后共 {len(players)} 名选手")

    # Step 2: 存入 DB（upsert，已有记录会更新）
    logger.info("正在写入数据库...")
    storage = get_storage()

    db_rows = []
    for p in players:
        db_rows.append({
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
            "ranks": {
                rk: {"return": p.get(fk)}
                for (_rt, (rk, fk)) in [
                    ("10004", ("总榜", "return_total")),
                    ("10003", ("年榜", "return_250d")),
                    ("10001", ("月榜", "return_20d")),
                    ("10000", ("周榜", "return_5d")),
                    ("10005", ("日榜", "return_daily")),
                ]
                if p.get(fk) is not None
            },
        })

    storage.save_players_batch(db_rows)
    logger.info(f"写入完成: {len(db_rows)} 条记录")

    # 统计
    with_total = sum(1 for p in players if p.get("return_total") is not None)
    with_daily = sum(1 for p in players if p.get("return_daily") is not None)
    logger.info(f"  有总收益数据: {with_total}/{len(players)}")
    logger.info(f"  有日收益数据: {with_daily}/{len(players)}")
    logger.info("=" * 60)
    logger.info("每日榜单数据抓取 - 完成")


if __name__ == "__main__":
    main()