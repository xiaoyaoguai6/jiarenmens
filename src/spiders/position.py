import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from src.spiders.base import BaseSpider
from src.config import POSITION_URL
from src.utils.logger import setup_logger
from src.storage.json_storage import JsonStorage

logger = setup_logger()


class PositionSpider(BaseSpider):
    """持仓爬虫"""

    def __init__(self):
        super().__init__()
        self.storage = JsonStorage()

    def fetch_positions(self, zh_id: str, uid: str = "") -> List[Dict[str, Any]]:
        """获取持仓数据"""
        url = f"{POSITION_URL}?zh={zh_id}&uid={uid}"
        logger.info(f"获取选手持仓: {zh_id}")

        html = self.fetch_page_with_playwright(url, timeout=60)
        if not html:
            logger.error(f"获取选手 {zh_id} 持仓失败")
            return []

        soup = self.parse_html(html)
        positions = self.parse_positions(soup, zh_id)

        if positions:
            self.storage.save_positions(zh_id, positions)
            logger.info(f"选手 {zh_id} 持仓获取成功, 共 {len(positions)} 条")

        return positions

    def parse_positions(self, soup: BeautifulSoup, zh_id: str) -> List[Dict[str, Any]]:
        """解析持仓数据"""
        positions = []
        page_text = soup.get_text()

        # 查找持仓表格或列表
        position_items = soup.select('.position-item, .stock-item, [class*="position"]')

        # 尝试从页面文本提取股票信息
        # 匹配格式: 股票名称 股票代码 成本价 当前价 盈亏比例 仓位比例
        stock_pattern = r'([^\s]{2,10})\s*(\d{6})\s*([\d.]+)\s*([\d.]+)\s*([-\d.]+)%\s*(\d+)%'
        matches = re.findall(stock_pattern, page_text)

        for match in matches:
            try:
                position = {
                    'zh_id': zh_id,
                    'stock_name': match[0],
                    'stock_code': match[1],
                    'cost_price': float(match[2]),
                    'current_price': float(match[3]),
                    'profit_ratio': float(match[4]),
                    'position_ratio': float(match[5]),
                    'update_time': ''
                }
                positions.append(position)
            except (ValueError, IndexError) as e:
                logger.warning(f"解析持仓项失败: {e}")
                continue

        # 如果正则匹配失败，尝试从表格提取
        if not positions:
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # 跳过表头
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 6:
                        try:
                            position = {
                                'zh_id': zh_id,
                                'stock_name': cells[0].get_text(strip=True),
                                'stock_code': cells[1].get_text(strip=True),
                                'cost_price': float(cells[2].get_text(strip=True)) if cells[2].get_text(strip=True) else 0.0,
                                'current_price': float(cells[3].get_text(strip=True)) if cells[3].get_text(strip=True) else 0.0,
                                'profit_ratio': float(cells[4].get_text(strip=True).replace('%', '')) if cells[4].get_text(strip=True) else 0.0,
                                'position_ratio': float(cells[5].get_text(strip=True).replace('%', '')) if cells[5].get_text(strip=True) else 0.0,
                                'update_time': ''
                            }
                            positions.append(position)
                        except (ValueError, IndexError) as e:
                            logger.warning(f"解析持仓表格失败: {e}")
                            continue

        return positions


def crawl_positions(zh_id: str, uid: str = "") -> List[Dict[str, Any]]:
    """爬取持仓数据"""
    spider = PositionSpider()
    return spider.fetch_positions(zh_id, uid)


if __name__ == "__main__":
    positions = crawl_positions("900304915", "5887346444580316")
    print(f"获取到 {len(positions)} 条持仓")
    for p in positions[:5]:
        print(p)
