# -*- coding: utf-8 -*-
"""Test zuhe/api and apistock/tran/getJson APIs."""
import sys, io, requests, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ZH_ID = "900013608"
UID = "2012094520785316"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)",
    "Referer": "https://groupwap.eastmoney.com",
})

# Test 1: zuhe/api/Topic/GetInfo
print("=== zuhe/api/Topic/GetInfo ===")
for base in ["https://emdcspzhapi.dfcfs.cn", "https://groupwap.eastmoney.com"]:
    url = "%s/zuhe/api/Topic/GetInfo" % base
    for params in [{"zh": ZH_ID}, {"id": ZH_ID}, {"combinationId": ZH_ID}]:
        try:
            r = s.get(url, params=params, timeout=10)
            if r.status_code == 200 and len(r.text) > 30:
                print("  %s %s => %d %s" % (base.split("//")[1][:30], str(params), r.status_code, r.text[:300]))
        except Exception as e:
            print("  ERROR: %s" % str(e)[:80])

# Test 2: zuhe/api/Topic/TopicList
print("\n=== zuhe/api/Topic/TopicList ===")
for base in ["https://emdcspzhapi.dfcfs.cn", "https://groupwap.eastmoney.com"]:
    url = "%s/zuhe/api/Topic/TopicList" % base
    for params in [{"uid": UID}, {"userId": UID}, {"zh": ZH_ID}]:
        try:
            r = s.get(url, params=params, timeout=10)
            if r.status_code == 200 and len(r.text) > 30:
                print("  %s %s => %d %s" % (base.split("//")[1][:30], str(params), r.status_code, r.text[:300]))
        except Exception as e:
            print("  ERROR: %s" % str(e)[:80])

# Test 3: apistock/tran/getJson with zuhe paths
print("\n=== apistock/tran/getJson ===")
for base in ["https://emdcspzhapi.dfcfs.cn", "https://groupwap.eastmoney.com"]:
    url = "%s/apistock/tran/getJson" % base
    for path in ["zuhe/api/Topic/GetInfo", "zuhe/api/Topic/TopicList", "zuheV64/JS.aspx"]:
        for parm in [json.dumps({"zh": ZH_ID}), json.dumps({"id": ZH_ID}), json.dumps({"uid": UID})]:
            try:
                r = s.post(url, data={"path": path, "parm": parm}, timeout=10)
                if r.status_code == 200 and len(r.text) > 30:
                    print("  POST %s path=%s parm=%s => %d %s" % (base.split("//")[1][:20], path, parm[:50], r.status_code, r.text[:300]))
            except Exception as e:
                pass

# Test 4: rtV1 with rt_zhuhe_yk_new
print("\n=== rtV1 rt_zhuhe_yk_new ===")
for params in [
    {"type": "rt_zhuhe_yk_new", "zh": ZH_ID, "appVer": "9001000"},
    {"type": "rt_zhuhe_yk_new", "zh": ZH_ID, "uid": UID, "appVer": "9001000"},
]:
    try:
        r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=10)
        d = r.json()
        print("  %s => result=%s data=%s" % (str(params), d.get("result"), json.dumps(d.get("data", ""), ensure_ascii=False)[:300]))
    except Exception as e:
        print("  ERROR: %s" % str(e)[:80])

# Test 5: Try POST to rtV1 with sign
print("\n=== rtV1 POST with sign ===")
for typ in ["rt_get_change", "rt_get_position", "rt_zhuhe_yk_new"]:
    params = {
        "plat": "wap", "version": "101", "product": "emguba",
        "appVer": "9001000", "deviceid": "4B977BC5-EAE3-43FC-9327-7B8E5127FE02",
        "ut": "", "ctoken": "",
        "type": typ, "zh": ZH_ID, "time": int(time.time() * 1000),
    }
    try:
        r = s.post("https://emdcspzhapi.dfcfs.cn/rtV1", data=params, timeout=10)
        d = r.json()
        print("  POST %s => result=%s data=%s" % (typ, d.get("result"), json.dumps(d.get("data", ""), ensure_ascii=False)[:200]))
    except Exception as e:
        print("  POST %s => ERROR: %s" % (typ, str(e)[:80]))

# Test 6: Try zuheV64/JS.aspx with different types
print("\n=== zuheV64/JS.aspx ===")
for base in ["https://push2em.eastmoney.com/em", "https://emdcspzhapi.dfcfs.cn"]:
    for ptype in ["get", "getPosition", "getTrade", "getDetail", "getInfo", "getStock", "getHold", "getChange"]:
        url = "%s/zuheV64/JS.aspx" % base
        try:
            r = s.get(url, params={"type": ptype, "zh": ZH_ID}, timeout=10)
            if r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower() and len(r.text) > 30:
                print("  %s type=%s => %d %s" % (base.split("//")[1][:20], ptype, r.status_code, r.text[:200]))
        except:
            pass

print("\nDone!")
