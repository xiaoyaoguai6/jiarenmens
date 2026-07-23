"""
构建全量股票代码缓存 (stock_codes.json)
使用腾讯财经批量查询生成全市场股票代码清单
"""
import json
import requests
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT = DATA_DIR / "stock_codes.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 已知的A股股票代码前缀
PREFIXES = {
    "000": "深证主板", "001": "深证主板", "002": "中小板", "003": "深证主板",
    "300": "创业板", "301": "创业板",
    "600": "上证主板", "601": "上证主板", "603": "上证主板", "605": "上证主板",
    "688": "科创板", "689": "科创板",
    "8": "北交所", "4": "老三板", "9": "B股",
    "159": "ETF", "510": "ETF", "511": "ETF", "512": "ETF", "513": "ETF",
    "515": "ETF", "516": "ETF", "517": "ETF", "518": "ETF",
    "560": "ETF", "561": "ETF", "562": "ETF", "563": "ETF",
    "588": "科创ETF",
}

def get_prefix(code):
    if len(code) >= 3:
        p3 = code[:3]
        if p3 in PREFIXES:
            return p3
    if len(code) >= 1:
        p1 = code[:1]
        if p1 in PREFIXES:
            return p1
    return code[:3]

print("正在通过腾讯财经API获取全市场股票数据...")

all_stocks = []
session = requests.Session()

# 用东财API获取所有股票代码（分页拉取，每页100）
def fetch_em_page(fs, page=1):
    url = f"http://80.push2.eastmoney.com/api/qt/clist/get?pn={page}&pz=100&po=1&np=1&fields=f12,f14&fid=f3&fs={fs}"
    try:
        resp = session.get(url, timeout=10)
        data = resp.json()
        items = data.get("data", {}).get("diff", [])
        total = data.get("data", {}).get("total", 0)
        return [{"code": str(i["f12"]), "name": i["f14"]} for i in items if i.get("f12") and i.get("f14")], total
    except:
        return [], 0

markets = [
    ("上证A股", "m:1+t:2,m:1+t:23"),
    ("深证A股", "m:0+t:6,m:0+t:80"),
    ("北交所", "m:0+t:81+s:2048"),
    ("ETF", "m:1+t:3,m:0+t:8"),
]

for label, fs in markets:
    for page in range(1, 200):  # max 200 pages
        items, total = fetch_em_page(fs, page)
        if not items or len(items) == 0:
            break
        all_stocks.extend(items)
        print(f"  {label} p{page}: {len(items)}/{total}")
        if len(items) < 100:
            break
        time.sleep(0.15)

# 去重
seen = set()
unique = []
for s in all_stocks:
    if s["code"] not in seen:
        seen.add(s["code"])
        unique.append(s)

# 按前缀分组
categories = {}
for s in unique:
    prefix = get_prefix(s["code"])
    if prefix not in categories:
        categories[prefix] = []
    categories[prefix].append(s)

output = {
    "stocks": unique,
    "categories": categories,
    "total": len(unique),
    "prefixes": sorted(categories.keys()),
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False)

print(f"\n✅ 股票代码缓存: {OUTPUT}")
print(f"   总计: {len(unique)} 只股票 | {len(categories)} 个前缀")
for p in sorted(categories.keys()):
    print(f"   {p}***: {len(categories[p])} 只")