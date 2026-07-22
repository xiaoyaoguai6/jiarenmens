"""
Try multiple approaches to get position data from East Money.
"""
import requests
import json
import time
import hashlib
import random
import string

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Referer": "https://groupwap.eastmoney.com",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
})

ZH_ID = "900113132"


def test(label, method, url, **kwargs):
    try:
        if method == "GET":
            r = session.get(url, timeout=15, **kwargs)
        else:
            r = session.post(url, timeout=15, **kwargs)
        text = r.text[:500]
        print(f"[{r.status_code}] {label}: {text}")
        return r
    except Exception as e:
        print(f"ERROR {label}: {e}")
        return None


print("=" * 80)
print("Approach 1: Try different rt_get_type values")
print("=" * 80)

types_to_try = [
    "rt_get_rank", "rt_get_info", "rt_get_position", "rt_get_change",
    "rt_get_detail", "rt_get_userinfo", "rt_get_stock", "rt_get_hold",
    "rt_get_holding", "rt_get_position_list", "rt_get_portfolio",
    "rt_get_trade", "rt_get_trade_list", "rt_get_position_detail",
    "rt_get_summary", "rt_get_overview", "rt_get_fund", "rt_get_asset",
    "rt_get_history", "rt_get_record", "rt_get_rebalance",
    "rt_get_stock_list", "rt_get_zjzh", "rt_get_combodetail",
    "rt_get_zjzh_position", "rt_get_zjzh_change", "rt_get_zjzh_info",
    "rt_get_zjzh_detail", "rt_get_zjzh_stock", "rt_get_zjzh_hold",
    "rt_get_zjzh_holding", "rt_get_zjzh_position_list",
    "rt_get_zjzh_portfolio", "rt_get_zjzh_trade",
]

for t in types_to_try:
    test(f"rtV1 type={t}", "GET",
         "https://emdcspzhapi.dfcfs.cn/rtV1",
         params={"type": t, "zh": ZH_ID, "appVer": "9001000"})

print()
print("=" * 80)
print("Approach 2: Try with Cookie-based auth")
print("=" * 80)

# First visit the page to get cookies
r = session.get(f"https://groupwap.eastmoney.com/group/reality/detail.html?zh={ZH_ID}", timeout=15)
print(f"Page visit cookies: {dict(session.cookies)}")

# Now try the API with cookies
for t in ["rt_get_info", "rt_get_position", "rt_get_change"]:
    test(f"rtV1 with cookies type={t}", "GET",
         "https://emdcspzhapi.dfcfs.cn/rtV1",
         params={"type": t, "zh": ZH_ID, "appVer": "9001000"})

print()
print("=" * 80)
print("Approach 3: Try with ct/ut tokens (anonymous)")
print("=" * 80)

for t in ["rt_get_info", "rt_get_position", "rt_get_change"]:
    test(f"rtV1 with tokens type={t}", "GET",
         "https://emdcspzhapi.dfcfs.cn/rtV1",
         params={
             "type": t, "zh": ZH_ID, "appVer": "9001000",
             "ctToken": "", "utToken": "", "uid": "",
         })

print()
print("=" * 80)
print("Approach 4: Try apistock/tran/getJson (api003 style)")
print("=" * 80)

api003_tests = [
    ("GET", "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson", {
        "path": "zuheV64/JS.aspx", "zh": ZH_ID
    }),
    ("POST", "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson", {
        "path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/detail.html",
        "zh": ZH_ID,
    }),
    ("POST", "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson", {
        "path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/detail.html",
        "urlParm": json.dumps({"zh": ZH_ID}),
    }),
]

for method, url, params in api003_tests:
    test(f"api003 {method} path={params.get('path','?')}", method, url, data=params)

print()
print("=" * 80)
print("Approach 5: Try web2.eastmoney.com APIs (web stock data)")
print("=" * 80)

web2_tests = [
    ("https://web2.eastmoney.com/zuhe/api/Trade/GetPositionList", {"zh": ZH_ID}),
    ("https://web2.eastmoney.com/zuhe/api/Trade/GetTradeList", {"zh": ZH_ID}),
    ("https://web2.eastmoney.com/zuhe/api/Zuhe/GetInfo", {"zh": ZH_ID}),
]

for url, params in web2_tests:
    test(f"web2 {url.split('/')[-1]}", "GET", url, params=params)

print()
print("=" * 80)
print("Approach 6: Try mguba API")
print("=" * 80)

mguba_tests = [
    ("https://mguba.eastmoney.com/interface/GetData?path=zuhe/api/Trade/GetPositionList", {"zh": ZH_ID}),
    ("https://mguba.eastmoney.com/interface/GetData?path=zuhe/api/Trade/GetTradeList", {"zh": ZH_ID}),
]

for url, params in mguba_tests:
    test(f"mguba {url.split('path=')[1]}", "GET", url, params=params)

print()
print("=" * 80)
print("Approach 7: Try datacenter-web for fund/portfolio data")
print("=" * 80)

datacenter_tests = [
    ("https://datacenter-web.eastmoney.com/api/data/v1/get", {
        "reportName": "RPT_ZUHE_POSITION",
        "columns": "ALL",
        "filter": f'(ZJZH="{ZH_ID}")',
    }),
    ("https://datacenter-web.eastmoney.com/api/data/v1/get", {
        "reportName": "RPT_ZUHE_TRADE",
        "columns": "ALL",
        "filter": f'(ZJZH="{ZH_ID}")',
    }),
]

for url, params in datacenter_tests:
    test(f"datacenter {params['reportName']}", "GET", url, params=params)

print()
print("Done!")
