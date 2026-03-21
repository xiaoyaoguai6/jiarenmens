import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from src.spiders.base import BaseSpider
from src.config import TRADE_URL
from src.utils.logger import setup_logger
from src.storage.json_storage import JsonStorage

logger = setup_logger()


def parse_position_ratio(position_str: str) -> float:
    """解析仓位字符串为数值"""
    if not position_str:
        return 0.0

    # 仓位映射
    position_map = {
        "满仓": 100,
        "9成以上": 95,
        "9成": 90,
        "8成": 80,
        "7成": 70,
        "6成": 60,
        "5成": 50,
        "4成": 40,
        "3成": 30,
        "2成": 20,
        "1成": 10,
        "1成以下": 5,
        "空仓": 0,
    }

    for key, value in position_map.items():
        if key in position_str:
            return value

    # 尝试提取数字
    match = re.search(r'(\d+)', position_str)
    if match:
        return float(match.group(1))

    return 0.0


def infer_trade_direction(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据仓位变化推断买入/卖出方向"""
    if not trades or len(trades) <= 1:
        # 如果只有一条记录，无法判断方向，默认为"调仓"
        for trade in trades:
            trade["direction"] = "调仓"
            trade["position_change"] = 0
        return trades

    # 按日期排序（从新到旧）
    sorted_trades = sorted(trades, key=lambda x: x.get("trade_date", ""), reverse=True)

    # 用于跟踪每只股票的历史仓位
    stock_history = {}  # {stock_code: [仓位, ...]}

    for i, trade in enumerate(sorted_trades):
        stock_code = trade.get("stock_code", "")
        current_position = parse_position_ratio(trade.get("position_ratio", ""))

        if stock_code not in stock_history:
            stock_history[stock_code] = []

        # 获取之前的历史仓位
        history = stock_history[stock_code]

        if not history:
            # 第一次出现，无法判断方向
            trade["direction"] = "调仓"
            trade["position_change"] = 0
        else:
            prev_position = history[-1]  # 最近一次的仓位
            change = current_position - prev_position

            if change > 0:
                trade["direction"] = "买入"
            elif change < 0:
                trade["direction"] = "卖出"
            else:
                trade["direction"] = "持有"
            trade["position_change"] = change

        # 更新历史
        history.append(current_position)
        stock_history[stock_code] = history

    # 按日期从旧到新排序返回
    return sorted_trades


class TradeSpider(BaseSpider):
    """调仓记录爬虫"""

    def __init__(self):
        super().__init__()
        self.storage = JsonStorage()

    def fetch_trades(self, zh_id: str, uid: str = "") -> List[Dict[str, Any]]:
        """获取调仓记录"""
        url = f"{TRADE_URL}?zh={zh_id}&uid={uid}"
        logger.info(f"获取选手调仓记录: {zh_id}")

        html = self.fetch_page_with_scroll(url, timeout=60, scroll_pause=0.5, max_scrolls=20)
        if not html:
            logger.error(f"获取选手 {zh_id} 调仓记录失败")
            return []

        soup = self.parse_html(html)
        trades = self.parse_trades(soup, zh_id)

        # 推断交易方向
        trades = infer_trade_direction(trades)

        if trades:
            self.storage.save_trades(zh_id, trades)
            logger.info(f"选手 {zh_id} 调仓记录获取成功, 共 {len(trades)} 条")

        return trades

    def parse_trades(self, soup: BeautifulSoup, zh_id: str) -> List[Dict[str, Any]]:
        """解析调仓记录"""
        trades = []
        page_text = soup.get_text()

        # 清理空白
        page_text = re.sub(r'\s+', ' ', page_text)

        # 匹配调仓记录格式
        # 格式: "2026-03-20 上能电气 300827 1笔 9成以上 44.000元"
        pattern = r'(\d{4}-\d{2}-\d{2})\s*([^\s\d]{2,10})\s*(\d{6})\s*(\d+)笔\s*(\S+)\s*([\d.]+)元'
        matches = re.findall(pattern, page_text)

        for match in matches:
            try:
                trade = {
                    'zh_id': zh_id,
                    'trade_date': match[0],
                    'stock_name': match[1],
                    'stock_code': match[2],
                    'trades': int(match[3]),
                    'position_ratio': match[4],
                    'position_value': float(match[5]),  # 成交均价
                    'direction': '',  # 待推断
                    'position_change': 0,  # 待计算
                }
                trades.append(trade)
            except (ValueError, IndexError) as e:
                logger.warning(f"解析调仓记录失败: {e}")
                continue

        return trades


def crawl_trades(zh_id: str, uid: str = "") -> List[Dict[str, Any]]:
    """爬取调仓记录"""
    spider = TradeSpider()
    return spider.fetch_trades(zh_id, uid)


if __name__ == "__main__":
    trades = crawl_trades("900304915", "")
    print(f"获取到 {len(trades)} 条调仓记录")
    for t in trades[:5]:
        print(t)
