from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# 按时间戳存储
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
DATA_BY_DATE = DATA_DIR / TIMESTAMP

PLAYERS_DIR = DATA_BY_DATE / "players"
POSITIONS_DIR = DATA_BY_DATE / "positions"
TRADES_DIR = DATA_BY_DATE / "trades"

# 最新的数据链接（软链接）
LATEST_DIR = DATA_DIR / "latest"

BASE_URL = "https://groupwap.eastmoney.com"

PLAYER_LIST_URL = f"{BASE_URL}/group/invest/reality.html"
PLAYER_INFO_URL = f"{BASE_URL}/group/reality/info.html"
POSITION_URL = f"{BASE_URL}/group/reality/detail.html"
TRADE_URL = f"{BASE_URL}/group/reality/change.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
}
