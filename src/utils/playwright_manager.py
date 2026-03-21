"""
Playwright 线程安全管理器

解决多线程环境下 Playwright 并发访问的问题：
- 使用 threading.Lock 确保同时只有一个线程可以使用 Playwright
- 每次操作创建独立的浏览器实例，避免状态污染
"""
import threading
import time
from contextlib import contextmanager
from typing import Optional, Generator

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from src.utils.logger import setup_logger

logger = setup_logger()

# 全局锁，确保 Playwright 操作串行化
_playwright_lock = threading.Lock()

# 全局 Playwright 实例（延迟初始化）
_playwright_instance = None


class PlaywrightManager:
    """线程安全的 Playwright 管理器（单例模式）"""

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._playwright = None
        self._initialized = True
        logger.debug("PlaywrightManager 初始化")

    def _get_playwright(self):
        """获取或初始化 Playwright 实例"""
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        return self._playwright

    def close(self):
        """关闭 Playwright 实例"""
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.warning(f"关闭 Playwright 时出错: {e}")
            self._playwright = None


@contextmanager
def get_playwright_context(
    timeout: int = 30,
    headless: bool = True,
    proxy: Optional[dict] = None
) -> Generator[tuple[Browser, Page], None, None]:
    """
    获取 Playwright 浏览器上下文的上下文管理器

    Args:
        timeout: 超时时间（秒）
        headless: 是否无头模式
        proxy: 代理配置，格式: {'server': 'http://host:port'}

    Yields:
        (browser, page): 浏览器实例和页面对象

    Usage:
        with get_playwright_context() as (browser, page):
            page.goto("https://example.com")
            content = page.content()
        # 浏览器和页面会在上下文结束时自动关闭
    """
    browser = None
    page = None

    try:
        # 获取锁（阻塞等待，直到获得锁）
        _playwright_lock.acquire()
        logger.debug("获得 Playwright 锁")

        # 启动 Playwright
        p = sync_playwright().start()
        logger.debug("Playwright 启动成功")

        try:
            # 启动参数
            launch_options = {'headless': headless}

            # 添加代理配置
            if proxy:
                launch_options['proxy'] = proxy

            # 创建浏览器实例
            browser = p.chromium.launch(**launch_options)
            logger.debug("Chromium 浏览器启动成功")

            # 创建新页面
            page = browser.new_page()
            logger.debug("新页面创建成功")

            # 释放锁，让上下文管理器可以继续
            _playwright_lock.release()

            yield (browser, page)

        except Exception as e:
            # 确保锁被释放
            if _playwright_lock.locked():
                _playwright_lock.release()
            raise e

    except Exception as e:
        logger.error(f"Playwright 上下文错误: {e}")
        raise e

    finally:
        # 清理资源
        try:
            if page:
                page.close()
            if browser:
                browser.close()
            p.stop()
            logger.debug("Playwright 资源已释放")
        except Exception as e:
            logger.warning(f"清理 Playwright 资源时出错: {e}")


def close_playwright_manager():
    """关闭全局 Playwright 管理器"""
    global _playwright_instance
    if _playwright_instance:
        _playwright_instance.close()
        _playwright_instance = None


# 预加载（可选，在主进程启动时调用）
def warm_up():
    """预热 Playwright（建议在主进程启动时调用一次）"""
    global _playwright_instance
    _playwright_instance = PlaywrightManager()
    _playwright_instance._get_playwright()
    logger.info("Playwright 预热完成")