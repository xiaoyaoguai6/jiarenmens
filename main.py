"""
东方财富实盘选手爬虫 - 优化版本
- 高并发爬取
- 按时间戳存储
- 支持断点续传
"""
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
from src.spiders.player_list import PlayerListSpider, crawl_player_list
from src.spiders.player_detail import PlayerDetailSpider, crawl_player_detail
from src.spiders.position import PositionSpider, crawl_positions
from src.spiders.trade import TradeSpider, crawl_trades
from src.storage.json_storage import JsonStorage, update_latest_symlink
from src.utils.logger import setup_logger
from src.utils.playwright_manager import warm_up

logger = setup_logger()
storage = JsonStorage()

# 并发配置
MAX_WORKERS = 20  # 降低并发数，避免被限流
REQUEST_DELAY = 0.3  # 增加请求间隔
SKIP_EXISTING = True  # 跳过已存在的文件


def crawl_player_data(zh_id: str, name: str) -> Tuple[str, str, Dict, List, List]:
    """爬取单个选手的所有数据"""
    try:
        if SKIP_EXISTING:
            detail = storage.load_player_detail(zh_id)
            if detail:
                positions = storage.load_positions(zh_id)
                trades = storage.load_trades(zh_id)
                return (zh_id, name, detail, positions, trades)

        # 并发爬取详情、持仓、调仓
        with ThreadPoolExecutor(max_workers=3) as executor:
            detail_future = executor.submit(crawl_player_detail, zh_id)
            positions_future = executor.submit(crawl_positions, zh_id)
            trades_future = executor.submit(crawl_trades, zh_id)

            detail = detail_future.result()
            time.sleep(REQUEST_DELAY)
            positions = positions_future.result()
            time.sleep(REQUEST_DELAY)
            trades = trades_future.result()

        return (zh_id, name, detail, positions, trades)
    except Exception as e:
        logger.error(f"爬取选手 {name}({zh_id}) 失败: {e}")
        return (zh_id, name, None, [], [])


def crawl_all_data(test_mode: bool = False, max_per_rank: int = 500, max_workers: int = 50):
    """爬取所有数据"""
    global MAX_WORKERS, REQUEST_DELAY, SKIP_EXISTING
    MAX_WORKERS = max_workers

    # 预热 Playwright（必须在创建线程池之前）
    logger.info("预热 Playwright...")
    warm_up()

    logger.info("=" * 60)
    logger.info(f"开始爬取东方财富实盘选手数据 (每榜单{max_per_rank}名, 并发数{max_workers})")
    logger.info("=" * 60)

    # Step 1: 获取选手列表
    logger.info("\n[Step 1] 获取选手列表...")
    player_list_spider = PlayerListSpider()
    players = player_list_spider.fetch_player_list(max_per_rank)

    if not players:
        logger.warning("未获取到选手列表")
        return

    logger.info(f"共获取 {len(players)} 个选手 (去重后)")

    if test_mode:
        players = players[:10]
        logger.info(f"测试模式: 只处理前 {len(players)} 个选手")

    # Step 2: 并发爬取选手数据
    logger.info(f"\n[Step 2] 并发获取选手数据 (并发数={max_workers}, 跳过已存在={SKIP_EXISTING})...")

    success_count = 0
    fail_count = 0
    skip_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_player = {
            executor.submit(crawl_player_data, p.get('zh_id'), p.get('name', '')): p
            for p in players
        }

        for future in as_completed(future_to_player):
            player = future_to_player[future]
            zh_id = player.get('zh_id')
            name = player.get('name', '')

            try:
                result = future.result()
                _, _, detail, positions, trades = result

                if detail:
                    if SKIP_EXISTING and storage.load_player_detail(zh_id):
                        skip_count += 1
                    else:
                        success_count += 1
                        logger.info(f"  ✓ {name}({zh_id}): 详情, {len(positions)}持仓, {len(trades)}调仓")
                else:
                    fail_count += 1
                    logger.warning(f"  ✗ {name}({zh_id}): 获取失败")

            except Exception as e:
                fail_count += 1
                logger.error(f"  ✗ {name}({zh_id}): 异常 {e}")

    # 更新latest链接
    update_latest_symlink()

    logger.info("\n" + "=" * 60)
    logger.info(f"数据爬取完成! 成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")
    logger.info("=" * 60)


def main():
    """主函数"""
    import sys
    import argparse

    # 先检查是否有--analyze
    if '--analyze' in sys.argv:
        from src.analysis.position_analyzer import analyze_positions
        # 移除--analyze参数后调用
        sys.argv = [a for a in sys.argv if a != '--analyze']
        analyze_positions()
        return

    parser = argparse.ArgumentParser(description='东方财富实盘选手爬虫')
    parser.add_argument('--test', action='store_true', help='测试模式(只处理10个选手)')
    parser.add_argument('--full', action='store_true', help='全量爬取(默认)')
    parser.add_argument('--limit', type=int, default=500, help='每榜单爬取数量(default: 500)')
    parser.add_argument('--workers', type=int, default=20, help='并发数(default: 20)')
    parser.add_argument('--no-skip', action='store_true', help='不跳过已存在的文件')
    args = parser.parse_args()

    global SKIP_EXISTING
    SKIP_EXISTING = not args.no_skip

    crawl_all_data(
        test_mode=args.test,
        max_per_rank=args.limit,
        max_workers=args.workers
    )


if __name__ == "__main__":
    main()
