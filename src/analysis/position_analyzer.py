"""
持仓分析器
- 统计持仓数量最多的股票
- 分析当日选手仓位分布
- 热门股票分析
"""
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional
from src.storage.json_storage import JsonStorage
from src.utils.logger import setup_logger

logger = setup_logger()
storage = JsonStorage()


class PositionAnalyzer:
    """持仓分析器"""

    def __init__(self, use_latest: bool = True):
        self.use_latest = use_latest
        self.storage = storage

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """获取所有选手的持仓数据"""
        positions = []
        player_ids = self.storage.get_all_player_ids()

        for zh_id in player_ids:
            pos = self.storage.load_positions(zh_id, use_latest=self.use_latest)
            if pos:
                for p in pos:
                    p['zh_id'] = zh_id
                positions.extend(pos)

        return positions

    def get_top_holdings(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取持仓数量最多的股票"""
        positions = self.get_all_positions()

        # 统计每只股票被多少选手持有
        stock_counter = Counter()
        stock_details = defaultdict(list)

        for pos in positions:
            stock_code = pos.get('stock_code', '')
            stock_name = pos.get('stock_name', '')
            if stock_code:
                stock_counter[stock_code] += 1
                stock_details[stock_code].append({
                    'name': stock_name,
                    'position_ratio': pos.get('position_ratio', 0),
                    'profit_ratio': pos.get('profit_ratio', 0),
                    'zh_id': pos.get('zh_id', '')
                })

        results = []
        for stock_code, count in stock_counter.most_common(top_n):
            details = stock_details[stock_code]
            avg_position = sum(d['position_ratio'] for d in details) / len(details) if details else 0
            avg_profit = sum(d['profit_ratio'] for d in details) / len(details) if details else 0

            results.append({
                'stock_code': stock_code,
                'stock_name': details[0]['name'] if details else '',
                'holder_count': count,
                'avg_position_ratio': round(avg_position, 2),
                'avg_profit_ratio': round(avg_profit, 2),
            })

        return results

    def get_position_distribution(self) -> Dict[str, Any]:
        """获取选手仓位分布"""
        player_ids = self.storage.get_all_player_ids()

        # 统计每个选手的总仓位
        position_levels = defaultdict(int)

        for zh_id in player_ids:
            positions = self.storage.load_positions(zh_id, use_latest=self.use_latest)
            if not positions:
                position_levels['空仓'] += 1
                continue

            total_position = sum(p.get('position_ratio', 0) for p in positions)

            if total_position == 0:
                level = '空仓'
            elif total_position < 10:
                level = '1成以下'
            elif total_position < 20:
                level = '1成'
            elif total_position < 30:
                level = '2成'
            elif total_position < 40:
                level = '3成'
            elif total_position < 50:
                level = '4成'
            elif total_position < 60:
                level = '5成'
            elif total_position < 70:
                level = '6成'
            elif total_position < 80:
                level = '7成'
            elif total_position < 90:
                level = '8成'
            elif total_position < 95:
                level = '9成'
            else:
                level = '9成以上/满仓'

            position_levels[level] += 1

        # 按顺序排列
        order = ['空仓', '1成以下', '1成', '2成', '3成', '4成', '5成', '6成', '7成', '8成', '9成', '9成以上/满仓']
        result = {k: position_levels.get(k, 0) for k in order if position_levels.get(k, 0) > 0}

        return result

    def get_sector_distribution(self) -> List[Dict[str, Any]]:
        """获取概念板块分布"""
        positions = self.get_all_positions()

        # 按股票代码分组，计算平均盈利
        stock_profits = defaultdict(list)
        for pos in positions:
            stock_code = pos.get('stock_code', '')
            if stock_code:
                stock_profits[stock_code].append(pos.get('profit_ratio', 0))

        # 统计盈利分布
        profit_ranges = defaultdict(int)
        for profits in stock_profits.values():
            avg_profit = sum(profits) / len(profits)
            if avg_profit < -10:
                profit_ranges['<-10%'] += 1
            elif avg_profit < -5:
                profit_ranges['-10%~-5%'] += 1
            elif avg_profit < 0:
                profit_ranges['-5%~0%'] += 1
            elif avg_profit < 5:
                profit_ranges['0%~5%'] += 1
            elif avg_profit < 10:
                profit_ranges['5%~10%'] += 1
            elif avg_profit < 20:
                profit_ranges['10%~20%'] += 1
            else:
                profit_ranges['>20%'] += 1

        return [{'range': k, 'count': v} for k, v in sorted(profit_ranges.items())]

    def get_top_performers(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取当日盈利最高的选手"""
        player_ids = self.storage.get_all_player_ids()
        performers = []

        for zh_id in player_ids:
            detail = self.storage.load_player_detail(zh_id, use_latest=self.use_latest)
            if detail:
                performers.append({
                    'zh_id': zh_id,
                    'name': detail.get('name', ''),
                    'daily_return': detail.get('daily_return', 0),
                    'total_return': detail.get('total_return', 0),
                })

        performers.sort(key=lambda x: x.get('daily_return', 0), reverse=True)
        return performers[:top_n]

    def generate_report(self) -> Dict[str, Any]:
        """生成完整分析报告"""
        logger.info("开始生成持仓分析报告...")

        top_holdings = self.get_top_holdings(20)
        position_dist = self.get_position_distribution()
        sector_dist = self.get_sector_distribution()
        top_performers = self.get_top_performers(10)

        # 统计总选手数和持仓股票数
        player_ids = self.storage.get_all_player_ids()
        positions = self.get_all_positions()
        unique_stocks = len(set(p.get('stock_code', '') for p in positions))

        report = {
            'summary': {
                'total_players': len(player_ids),
                'total_positions': len(positions),
                'unique_stocks': unique_stocks,
            },
            'top_holdings': top_holdings,
            'position_distribution': position_dist,
            'profit_distribution': sector_dist,
            'top_performers': top_performers,
        }

        logger.info(f"分析完成: {len(player_ids)}选手, {len(positions)}持仓, {unique_stocks}只股票")
        return report

    def save_report(self, output_path: str = None):
        """保存分析报告"""
        report = self.generate_report()

        if output_path is None:
            from src.config import DATA_BY_DATE
            output_path = DATA_BY_DATE / "analysis_report.json"

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"分析报告已保存到 {output_path}")
        return report


def analyze_positions():
    """命令行分析入口"""
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description='持仓分析')
    parser.add_argument('--dir', type=str, default=None, help='指定数据文件夹（如 20260322_011334）')
    parser.add_argument('--latest', action='store_true', default=False, help='使用最新数据')
    parser.add_argument('--output', type=str, default=None, help='输出文件路径')
    args = parser.parse_args()

    # 确定数据目录
    if args.dir:
        data_path = Path(__file__).parent.parent.parent / 'data' / args.dir
        if not data_path.exists():
            print(f"错误: 数据目录不存在 {data_path}")
            return
    else:
        # 使用 latest
        data_path = Path(__file__).parent.parent.parent / 'data' / 'latest'

    print(f"分析数据目录: {data_path}")

    # 加载数据
    players_dir = data_path / 'players'
    positions_dir = data_path / 'positions'
    trades_dir = data_path / 'trades'

    # 获取所有选手
    player_files = list(players_dir.glob('*.json'))
    player_files = [f for f in player_files if f.name not in ['players.json', '总榜.json', '年榜.json', '月榜.json', '周榜.json', '日榜.json']]

    print(f"找到 {len(player_files)} 个选手")

    # 统计
    from collections import Counter, defaultdict

    stock_counter = Counter()
    stock_profits = defaultdict(list)
    stock_details = defaultdict(list)
    position_levels = defaultdict(int)
    performers = []

    for pf in player_files:
        zh_id = pf.stem
        try:
            with open(pf, 'r', encoding='utf-8') as f:
                detail = json.load(f)
        except:
            continue

        # 加载持仓
        pos_file = positions_dir / f'{zh_id}.json'
        positions = []
        if pos_file.exists():
            with open(pos_file, 'r', encoding='utf-8') as f:
                positions = json.load(f)

        # 统计股票
        total_position = 0
        for pos in positions:
            stock_code = pos.get('stock_code', '')
            if stock_code:
                stock_counter[stock_code] += 1
                stock_profits[stock_code].append(pos.get('profit_ratio', 0))
                stock_details[stock_code].append({
                    'name': pos.get('stock_name', ''),
                    'position_ratio': pos.get('position_ratio', 0),
                    'zh_id': zh_id
                })
            total_position += pos.get('position_ratio', 0)

        # 仓位分布
        if total_position == 0:
            position_levels['空仓'] += 1
        elif total_position < 30:
            position_levels['3成以下'] += 1
        elif total_position < 50:
            position_levels['3-5成'] += 1
        elif total_position < 70:
            position_levels['5-7成'] += 1
        elif total_position < 90:
            position_levels['7-9成'] += 1
        else:
            position_levels['9成以上'] += 1

        # 当日盈利
        if detail.get('daily_return'):
            performers.append({
                'name': detail.get('name', zh_id),
                'zh_id': zh_id,
                'daily_return': detail.get('daily_return', 0),
                'total_return': detail.get('total_return', 0),
            })

    # 输出报告
    print("\n" + "=" * 50)
    print("持仓分析报告")
    print("=" * 50)
    print(f"\n【概览】")
    print(f"  选手总数: {len(player_files)}")
    print(f"  涉及股票: {len(stock_counter)}只")

    print(f"\n【持仓最多的股票 Top 10】")
    for i, (code, count) in enumerate(stock_counter.most_common(10), 1):
        details = stock_details[code]
        name = details[0]['name'] if details else code
        avg_pos = sum(d['position_ratio'] for d in details) / len(details) if details else 0
        avg_profit = sum(stock_profits[code]) / len(stock_profits[code]) if stock_profits[code] else 0
        print(f"  {i}. {name}({code}): {count}人持有, 平均仓位{avg_pos:.1f}%, 平均盈利{avg_profit:.2f}%")

    print(f"\n【仓位分布】")
    for k, v in sorted(position_levels.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}人")

    performers.sort(key=lambda x: x['daily_return'], reverse=True)
    print(f"\n【当日盈利Top 10】")
    for i, p in enumerate(performers[:10], 1):
        print(f"  {i}. {p['name']}: 日{p['daily_return']:.2f}%, 总{p['total_return']:.2f}%")

    print()


if __name__ == "__main__":
    analyze_positions()
