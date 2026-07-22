# -*- coding: utf-8 -*-
"""Test rt_zhuhe_yk_new and zuheV64 via apistock/tran/getJson."""
import sys, io, requests, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ZH_ID = "900013608"
UID = "2012094520785316"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)",
    "Referer": "https://groupwap.eastmoney.com",
})

# Test 1: rt_zhuhe_yk_new with all params from JS
print("=== rt_zhuhe_yk_new ===")
for ykType in ["20", "250", "5", "1", "10"]:
    for indexCode in ["000300", "000001"]:
        params = {
            "type": "rt_zhuhe_yk_new",
            "zh": ZH_ID,
            "recIdx": "0",
            "recCnt": "100",
            "ykType": ykType,
            "indexCode": indexCode,
            "appVer": "9001000",
        }
        try:
            r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=10)
            d = r.json()
            result = d.get("result", "?")
            data = d.get("data")
            if result == "0" and data:
                print("  ** ykType=%s index=%s => result=%s count=%s" % (ykType, indexCode, result, data.get("count", "?")))
                print("     %s" % json.dumps(data, ensure_ascii=False)[:500])
            else:
                print("     ykType=%s index=%s => result=%s" % (ykType, indexCode, result))
        except Exception as e:
            print("     ykType=%s index=%s => ERROR: %s" % (ykType, indexCode, str(e)[:80]))

# Test 2: zuheV64/JS.aspx via apistock/tran/getJson
print("\n=== zuheV64 via apistock/tran/getJson ===")
for type_val in ["rt_zhuhe_yk_new", "zhuhe_yk_new", "get", "getPosition", "getTrade"]:
    urlParm = json.dumps({"type": type_val, "zh": ZH_ID})
    try:
        r = s.post("https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson",
                    data={"path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/detail.html", "urlParm": urlParm},
                    timeout=10)
        if r.status_code == 200 and len(r.text) > 30:
            print("  ** type=%s => %d %s" % (type_val, r.status_code, r.text[:500]))
        else:
            print("     type=%s => %d len=%d" % (type_val, r.status_code, len(r.text)))
    except Exception as e:
        print("     type=%s => ERROR: %s" % (type_val, str(e)[:80]))

# Test 3: Try rt_zhuhe_yk_new for multiple players from rank
print("\n=== rt_zhuhe_yk_new for multiple players ===")
r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params={
    "type": "rt_get_rank", "rankType": "10004", "recIdx": 0, "recCnt": 5, "rankid": 0, "appVer": "9001000"
}, timeout=15)
players = r.json()["data"]

for p in players:
    zh = p.get("zjzh", "")
    params = {
        "type": "rt_zhuhe_yk_new",
        "zh": zh,
        "recIdx": "0",
        "recCnt": "100",
        "ykType": "20",
        "indexCode": "000300",
        "appVer": "9001000",
    }
    try:
        r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=10)
        d = r.json()
        if d.get("result") == "0" and d.get("data"):
            data = d["data"]
            print("  zh=%s name=%s ykv=%s fensi=%s combos=%s" % (
                zh, data.get("userName", "?"), data.get("ykv", "?"),
                data.get("fensi", "?"), data.get("count", "?")))
        else:
            print("  zh=%s => result=%s" % (zh, d.get("result", "?")))
    except Exception as e:
        print("  zh=%s => ERROR: %s" % (zh, str(e)[:80]))

print("\nDone!")
