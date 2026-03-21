"""
东方财富实盘选手爬虫 - 基础爬虫类

优化版本：
- 使用线程安全的 Playwright 管理器
- 高并发爬取
- 按时间戳存储
- 支持断点续传
"""
import os
import time
import requests
from typing import Optional
from bs4 import BeautifulSoup
from src.config import HEADERS
from src.utils.logger import setup_logger
from src.utils.proxy_pool import get_proxy_pool
from src.utils.playwright_manager import get_playwright_context

logger = setup_logger()

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

# 是否启用代理池
USE_PROXY_POOL = os.environ.get('USE_PROXY_POOL', 'false').lower() == 'true'

# 获取代理池实例
_proxy_pool = None


def _get_proxy_pool():
    """获取代理池"""
    global _proxy_pool
    if _proxy_pool is None:
        _proxy_pool = get_proxy_pool()
    return _proxy_pool


class BaseSpider:
    """基础爬虫类"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_page(self, url: str, timeout: int = 30) -> Optional[str]:
        """使用requests获取页面"""
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"requests获取失败: {e}, 尝试使用playwright")
            return None

    def fetch_page_with_playwright(self, url: str, timeout: int = 30, retries: int = MAX_RETRIES) -> Optional[str]:
        """使用playwright获取动态页面（带重试和代理）"""
        proxy_pool = _get_proxy_pool() if USE_PROXY_POOL else None
        last_proxy = None

        for attempt in range(retries):
            proxy_config = None

            try:
                # 获取代理配置
                if proxy_pool:
                    proxy = proxy_pool.get()
                    if proxy:
                        last_proxy = proxy
                        proxy_str = proxy.http.replace('http://', '')
                        proxy_config = {'server': f'http://{proxy_str}'}
                        logger.debug(f"使用代理: {proxy.http}")

                # 使用线程安全的 Playwright 上下文
                with get_playwright_context(timeout=timeout, proxy=proxy_config) as (browser, page):
                    page.goto(url, timeout=timeout * 1000)
                    page.wait_for_load_state('networkidle', timeout=timeout * 1000)
                    content = page.content()

                    # 标记代理成功
                    if last_proxy and proxy_pool:
                        proxy_pool.mark_success(last_proxy)

                    return content

            except Exception as e:
                # 标记代理失败
                if last_proxy and proxy_pool:
                    proxy_pool.mark_failed(last_proxy)
                    last_proxy = None

                if attempt < retries - 1:
                    logger.warning(f"playwright获取失败 (尝试 {attempt+1}/{retries}): {e}, 重试中...")
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"playwright获取失败: {e}")
                    return None

        return None

    def fetch_page_with_scroll(self, url: str, timeout: int = 30, scroll_pause: float = 0.5, max_scrolls: int = 20, retries: int = MAX_RETRIES) -> Optional[str]:
        """使用playwright获取动态页面并滚动加载更多内容（带重试和代理）"""
        proxy_pool = _get_proxy_pool() if USE_PROXY_POOL else None
        last_proxy = None

        for attempt in range(retries):
            proxy_config = None

            try:
                # 获取代理配置
                if proxy_pool:
                    proxy = proxy_pool.get()
                    if proxy:
                        last_proxy = proxy
                        proxy_str = proxy.http.replace('http://', '')
                        proxy_config = {'server': f'http://{proxy_str}'}

                # 使用线程安全的 Playwright 上下文
                with get_playwright_context(timeout=timeout, proxy=proxy_config) as (browser, page):
                    page.goto(url, timeout=timeout * 1000)
                    page.wait_for_load_state('networkidle', timeout=timeout * 1000)

                    # 滚动页面加载更多数据
                    for i in range(max_scrolls):
                        page.evaluate("window.scrollBy(0, 500)")
                        page.wait_for_timeout(int(scroll_pause * 1000))

                        # 尝试点击"加载更多"按钮
                        try:
                            load_more = page.locator('text=加载更多').first
                            if load_more.is_visible():
                                load_more.click()
                                page.wait_for_timeout(int(scroll_pause * 1000))
                        except Exception:
                            # 忽略加载更多按钮的错误
                            pass

                    content = page.content()

                    # 标记代理成功
                    if last_proxy and proxy_pool:
                        proxy_pool.mark_success(last_proxy)

                    return content

            except Exception as e:
                # 标记代理失败
                if last_proxy and proxy_pool:
                    proxy_pool.mark_failed(last_proxy)
                    last_proxy = None

                if attempt < retries - 1:
                    logger.warning(f"playwright滚动获取失败 (尝试 {attempt+1}/{retries}): {e}, 重试中...")
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"playwright滚动获取失败: {e}")
                    return None

        return None

    def get_page_content(self, url: str, use_playwright: bool = False) -> Optional[str]:
        """获取页面内容，优先使用requests，失败则使用playwright"""
        content = self.fetch_page(url)
        if content:
            return content
        if use_playwright:
            return self.fetch_page_with_playwright(url)
        return None

    def parse_html(self, html: str) -> BeautifulSoup:
        """解析HTML"""
        return BeautifulSoup(html, 'lxml')