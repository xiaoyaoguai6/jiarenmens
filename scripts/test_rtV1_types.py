"""Quick test: what rtV1 type values return actual data?"""
import requests, json

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)",
    "Referer": "https://groupwap.eastmoney.com",
})

ZH = "900113132"
API = "https://emdcspzhapi.dfcfs.cn/rtV1"

print("=== rt_get_rank (baseline) ===")
r = s.get(API, params={"type": "rt_get_rank", "rankType": "10004", "recIdx": 0, "recCnt": 2, "rankid": 0, "appVer": "9001000"}, timeout=15)
d = r.json()
print("  result=%s, data count=%d" % (d.get("result"), len(d.get("data", []))))
if d.get("data"):
    print("  sample keys: %s" % list(d["data"][0].keys()))

types_to_try = [
    "rt_get_info", "rt_get_position", "rt_get_change", "rt_get_trade",
    "rt_get_detail", "rt_get_stock", "rt_get_hold", "rt_get_holding",
    "rt_get_asset", "rt_get_summary", "rt_get_overview", "rt_get_fund",
    "rt_get_history", "rt_get_record", "rt_get_rebalance",
    "rt_get_combodetail", "rt_get_zjzh",
    "rt_get_zjzh_info", "rt_get_zjzh_position", "rt_get_zjzh_change",
    "rt_get_portfolio", "rt_get_combination", "rt_get_combination_info",
]

print("\n=== Testing rtV1 type variants ===")
for t in types_to_try:
    try:
        r = s.get(API, params={"type": t, "zh": ZH, "appVer": "9001000"}, timeout=10)
        d = r.json()
        result = d.get("result", "?")
        msg = str(d.get("msg", ""))[:60]
        data = d.get("data")
        data_preview = ""
        if data:
            if isinstance(data, list) and len(data) > 0:
                data_preview = "list[%d]" % len(data)
                if isinstance(data[0], dict):
                    data_preview += " keys=%s" % list(data[0].keys())[:8]
            elif isinstance(data, dict):
                data_preview = "dict keys=%s" % list(data.keys())[:10]
            else:
                data_preview = str(data)[:100]
        if result != "-10000" and data:
            print("  ** %s: result=%s, msg=%s, data=%s" % (t, result, msg, data_preview))
        else:
            print("     %s: result=%s, msg=%s" % (t, result, msg))
    except Exception as e:
        print("     %s: ERROR %s" % (t, e))

print("\nDone!")
