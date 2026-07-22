import requests, json

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)",
})

zh = "900113132"

# 1) Try rtV1 with deviceid and more params
print("=== rtV1 with extra params ===")
extra_params = [
    {"type": "rt_get_info", "zh": zh, "deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA", "plat": "wap", "appVer": "9001000"},
    {"type": "rt_get_info", "zh": zh, "deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA", "plat": "wap", "product": "shipan", "version": "101", "appVer": "9001000"},
    {"type": "rt_get_info", "zh": zh, "deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA", "plat": "wap", "product": "guba", "version": "101", "ctoken": "", "utoken": "", "appVer": "9001000"},
    {"type": "rt_get_position", "zh": zh, "deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA", "plat": "wap", "appVer": "9001000"},
    {"type": "rt_get_change", "zh": zh, "deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA", "plat": "wap", "appVer": "9001000"},
]
for p in extra_params:
    r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=p, timeout=30)
    d = r.json()
    print("  type={:20s} result={:>6s} msg={}".format(p["type"], d.get("result", "?"), d.get("message","")[:80]))

# 2) Try guba API endpoint
print()
print("=== guba zuhe/api/Topic/GetInfo ===")
guba_url = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson"
guba_params = {
    "path": "zuhe/api/Topic/GetInfo",
    "parm": json.dumps([
        {"deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA"},
        {"plat": "wap"},
        {"product": "guba"},
        {"version": "101"},
        {"id": zh},
        {"ctoken": ""},
        {"utoken": ""},
    ]),
}
r = s.post(guba_url, data=guba_params, timeout=30)
print("  status={}, text[0:500]={}".format(r.status_code, r.text[:500]))

# 3) Try different dfcfs.cn paths 
print()
print("=== Other dfcfs.cn paths ===")
for path in ["/apistock/tran/getJson", "/rtV1", "/zuhe/api/Topic/GetInfo"]:
    params = {"type": "rt_get_rank", "rankType": "10005", "recIdx": 0, "recCnt": 1, "rankid": 0}
    url = "https://emdcspzhapi.dfcfs.cn" + path
    r = s.get(url, params=params, timeout=30)
    print("  GET {}: status={}, text[0:200]={}".format(path, r.status_code, r.text[:200]))

# 4) Try push2.eastmoney.com 
print()
print("=== push2.eastmoney.com zuhe API ===")
r = s.get("https://push2.eastmoney.com/api/qt/clist/get", params={
    "pn": "1", "pz": "20", "po": "1", "np": "1",
    "fltt": "2", "invt": "2", "fid": "f3",
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f15,f16,f17,f18",
}, timeout=30)
print("  push2 status={}, text[0:300]={}".format(r.status_code, r.text[:300]))
