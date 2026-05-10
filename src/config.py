from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

BASE_URL = "https://groupwap.eastmoney.com"

PLAYER_LIST_URL = f"{BASE_URL}/group/invest/reality.html"
PLAYER_INFO_URL = f"{BASE_URL}/group/reality/info.html"
POSITION_URL = f"{BASE_URL}/group/reality/detail.html"
TRADE_URL = f"{BASE_URL}/group/reality/change.html"

# groupwap.eastmoney.com 是移动端 H5 站点，桌面 UA 会被弹"前往 APP"
# 所以全程用 iPhone Mobile Safari UA + 移动 viewport
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Mobile/15E148 Safari/604.1"
)

# 移动设备模拟参数（与 USER_AGENT 配套，同时给 Playwright 和 requests 使用）
MOBILE_VIEWPORT = {"width": 414, "height": 896}
DEVICE_SCALE_FACTOR = 3

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": BASE_URL,
}