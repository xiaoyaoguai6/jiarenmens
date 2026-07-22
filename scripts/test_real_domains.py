# -*- coding: utf-8 -*-
"""测试东方财富APP真实域名"""
import sys, io, json, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

ZH = "900023658"

# 测试 emcontestapi.eastmoney.com（从Fiddler抓包发现的真实域名）
print("=== emcontestapi.eastmoney.com ===")
test_paths = [
    "/rtV1",
    "/rtV1?type=rt_get_rank&rankType=10004&recIdx=0&recCnt=3&rankid=0&appVer=9001000",
    "/rtV1?type=rt_get_info&zh=%s&appVer=9001000" % ZH,
    "/rtV1?type=rt_get_position&zh=%s&appVer=9001000" % ZH,
    "/Tran/GetData",
    "/apistock/Tran/GetData",
    "/rspThird/community/positionlist_handler",
    "/rspThird/community/tradelist_handler",
    "/rspThird/community/detail_handler",
]

for path in test_paths:
    url = "https://emcontestapi.eastmoney.com" + path
    try:
        if "Tran/GetData" in path or "handler" in path:
            r = s.post(url, json={"zh": ZH, "appVer": "9001000"}, timeout=10)
        else:
            r = s.get(url, timeout=10)
        body = r.text[:200]
        print("  [%d] %s => %s" % (r.status_code, path[:60], body))
    except Exception as e:
        print("  [ERR] %s => %s" % (path[:60], str(e)[:80]))

# 测试其他可能的域名
print("\n=== 其他域名 ===")
domains = [
    "https://emcontestapi.eastmoney.com",
    "https://emappapi.eastmoney.com",
    "https://emapi.eastmoney.com",
    "https://api.eastmoney.com",
    "https://shipanapi.eastmoney.com",
    "https://zuheapi.eastmoney.com",
]

for base in domains:
    url = base + "/rtV1?type=rt_get_rank&rankType=10004&recIdx=0&recCnt=1&rankid=0&appVer=9001000"
    try:
        r = s.get(url, timeout=8)
        body = r.text[:150]
        result = "?"
        try:
            d = json.loads(body)
            result = d.get("result", d.get("RCode", d.get("status", "?")))
        except:
            pass
        print("  [%d] %s => result=%s %s" % (r.status_code, base.split("//")[1], result, body[:80]))
    except Exception as e:
        print("  [ERR] %s => %s" % (base.split("//")[1], str(e)[:60]))

# 测试 emdcspzhapi 的 /Tran/GetData POST 格式
print("\n=== emdcspzhapi /Tran/GetData POST格式 ===")
body_data = {
    "url": "rtV1",
    "type": "rt_get_info",
    "data": {"zh": ZH, "appVer": "9001000"},
    "track": "sys_%d" % int(time.time() * 1000) if 'time' in dir() else "sys_123",
    "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH,
}
try:
    r = s.post("https://emdcspzhapi.dfcfs.cn/Tran/GetData", json=body_data, timeout=10)
    print("  [%d] %s" % (r.status_code, r.text[:200]))
except Exception as e:
    print("  [ERR] %s" % str(e)[:80])

# 测试 emstockdiag 网关
print("\n=== emstockdiag 网关 ===")
for path in [
    "rspThird/community/positionlist_handler",
    "rspThird/community/tradelist_handler",
    "rspThird/community/detail_handler",
    "rspThird/community/stocklist_handler",
    "v4/mobileadapter/gszcount",
    "v4/mobileadapter/positionlist",
    "v4/mobileadapter/tradelist",
]:
    body = {
        "path": path,
        "parm": json.dumps({"zh": ZH, "appVer": "9001000"}),
        "header": {"appkey": "a8157f5ef970edda2c103e192b6dc3e5", "Referer": "http://www.eastmoney.com"},
        "track": "sys_123",
        "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH,
    }
    try:
        r = s.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData", json=body, timeout=10)
        d = r.json()
        rcode = d.get("RCode", "?")
        rdata = str(d.get("RData", ""))[:100]
        state = "?"
        try:
            inner = json.loads(d.get("RData", "{}"))
            state = inner.get("state", "?")
        except:
            pass
        print("  [%s] %s => RCode=%s state=%s %s" % ("OK" if state == 0 else "??", path, rcode, state, rdata))
    except Exception as e:
        print("  [ERR] %s => %s" % (path, str(e)[:60]))
