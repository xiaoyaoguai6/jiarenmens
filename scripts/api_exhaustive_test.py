import requests, json, sys

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)",
    "Referer": "https://groupwap.eastmoney.com",
    "Origin": "https://groupwap.eastmoney.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Requested-With": "com.eastmoney.android.berlin",
})

zh = sys.argv[1] if len(sys.argv) > 1 else "900113132"

print("=== GET rtV1 tests ===")
params_list = [
    {"type": "rt_get_rank", "rankType": "10005", "recIdx": 0, "recCnt": 1, "rankid": 0, "appVer": "9001000"},
    {"type": "rt_get_info", "zh": zh, "appVer": "9001000"},
    {"type": "rt_get_info", "zh": zh, "zjzh": zh, "userid": "3043345941133016", "appVer": "9001000"},
    {"type": "rt_get_newest_position", "zh": zh, "appVer": "9001000"},
    {"type": "rt_get_newest_position", "zjzh": zh, "appVer": "9001000"},
    {"type": "rt_get_position", "zh": zh, "appVer": "9001000"},
    {"type": "rt_get_change", "zh": zh, "appVer": "9001000"},
    {"type": "rt_zh_detail", "zh": zh, "zjzh": zh, "appVer": "9001000"},
    {"type": "rt_player_info", "zh": zh, "appVer": "9001000"},
    {"type": "rt_get_zuhe_position", "zh": zh, "appVer": "9001000"},
    {"type": "rt_get_concern_list", "recIdx": 0, "recCnt": 20, "appVer": "9001000"},
]

for params in params_list:
    try:
        r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=30)
        d = r.json()
        result = d.get("result", "N/A")
        msg = d.get("message", "")[:80]
        dc = len(d.get("data", [])) if isinstance(d.get("data"), list) else 0
        print("  type={:30s} result={:>6s}  data_count={:>3d}  msg={}".format(params["type"], result, dc, msg))
        if d.get("data"):
            preview = json.dumps(d["data"], ensure_ascii=False)[:300]
            print("    DATA: {}".format(preview))
    except Exception as e:
        print("  type={:30s} ERROR: {}".format(params["type"], e))

print()
print("=== POST tests ===")
for params in [{"type": "rt_get_info", "zh": zh, "appVer": "9001000"}, {"type": "rt_get_position", "zh": zh, "appVer": "9001000"}]:
    try:
        r = s.post("https://emdcspzhapi.dfcfs.cn/rtV1", data=params, timeout=30)
        d = r.json()
        print("  POST type={:30s} result={}  msg={}".format(params["type"], d.get("result", "?"), d.get("message", "")[:80]))
    except Exception as e:
        print("  POST type={:30s} ERROR: {}".format(params["type"], e))

print()
print("=== apistock/tran/getJson tests ===")
proxy_url = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson"
proxy_tests = [
    {"path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html", "urlParm": json.dumps({"zh": zh})},
    {"path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html", "urlParm": json.dumps({"type": "rt_get_info", "zh": zh})},
    {"path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html", "urlParm": json.dumps({"zjzh": zh})},
    {"path": "zuheV64/JS.aspx", "parm": json.dumps({"type": "rt_get_info", "zh": zh})},
]
for data in proxy_tests:
    try:
        r = s.post(proxy_url, data=data, timeout=30)
        d = r.json()
        print("  {} => result={} msg={}".format(json.dumps(data, ensure_ascii=False)[:120], d.get("result"), d.get("message", "")[:80]))
    except Exception as e:
        print("  {} => ERROR: {}".format(json.dumps(data, ensure_ascii=False)[:120], e))
