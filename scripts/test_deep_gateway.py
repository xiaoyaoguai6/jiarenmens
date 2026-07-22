# -*- coding: utf-8 -*-
"""深入测试emstockdiag网关和rspThird API"""
import sys, io, json, requests, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

ZH = "900023658"
APPKEY = "a8157f5ef970edda2c103e192b6dc3e5"
PAGE_URL = "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH

# 1. 测试 gszcount 的完整参数
print("=== gszcount 完整参数 ===")
cid_values = [
    "", "test", ZH,
    "9f69c1bcff839a3202625794b00c75e3",  # 之前抓到的cid
]
for cid in cid_values:
    body = {
        "path": "v4/mobileadapter/gszcount",
        "parm": json.dumps({"cid": cid, "zh": ZH}) if cid else json.dumps({"zh": ZH}),
        "header": {"appkey": APPKEY, "Referer": "http://www.eastmoney.com", "ut": "", "ct": ""},
        "track": "sys_%d" % int(time.time() * 1000),
        "pageUrl": PAGE_URL,
    }
    try:
        r = s.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData", json=body, timeout=10)
        d = r.json()
        rdata = d.get("RData", "")
        print("  cid='%s' => RCode=%s RData=%s" % (cid[:20], d.get("RCode"), str(rdata)[:200]))
    except Exception as e:
        print("  cid='%s' => ERR: %s" % (cid[:20], str(e)[:60]))

# 2. 测试 rspThird handlers 的不同参数格式
print("\n=== rspThird handlers 不同参数 ===")
handlers = [
    "rspThird/community/positionlist_handler",
    "rspThird/community/tradelist_handler",
    "rspThird/community/detail_handler",
    "rspThird/community/stocklist_handler",
    "rspThird/community/info_handler",
]

parm_formats = [
    {"zh": ZH},
    {"zh": ZH, "appVer": "9001000"},
    {"zjzh": ZH},
    {"combinationId": ZH},
    {"cid": ZH},
    {"userId": "2012094520785316"},
    {"uid": "2012094520785316"},
]

for handler in handlers:
    name = handler.split("/")[-1]
    for parm in parm_formats:
        body = {
            "path": handler,
            "parm": json.dumps(parm),
            "header": {"appkey": APPKEY, "Referer": "http://www.eastmoney.com", "ut": "", "ct": ""},
            "track": "sys_%d" % int(time.time() * 1000),
            "pageUrl": PAGE_URL,
        }
        try:
            r = s.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData", json=body, timeout=10)
            d = r.json()
            rcode = d.get("RCode", "?")
            rdata = str(d.get("RData", ""))[:100]
            if rcode != 10:  # 只显示非默认响应
                print("  %s parm=%s => RCode=%s %s" % (name, json.dumps(parm)[:40], rcode, rdata))
        except:
            pass

# 3. 测试 emdcspzhapi 的其他端点
print("\n=== emdcspzhapi 其他端点 ===")
endpoints = [
    ("GET", "https://emdcspzhapi.dfcfs.cn/rtV1", {"type": "rt_get_rank", "rankType": "10004", "recIdx": "0", "recCnt": "3", "rankid": "0", "appVer": "9001000"}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/rtV1", {"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/srtV1", {"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/srtV1", {"type": "rt_get_position", "zh": ZH, "appVer": "9001000"}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/rtV2", {"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/rtV3", {"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/api/v1/position", {"zh": ZH}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/api/v1/detail", {"zh": ZH}),
    ("GET", "https://emdcspzhapi.dfcfs.cn/zuhe/api/Topic/GetInfo", {"zh": ZH}),
    ("POST", "https://emdcspzhapi.dfcfs.cn/zuhe/api/Topic/GetInfo", {"zh": ZH}),
]

for method, url, params in endpoints:
    try:
        if method == "GET":
            r = s.get(url, params=params, timeout=10)
        else:
            r = s.post(url, json=params, timeout=10)
        body = r.text[:150]
        try:
            d = json.loads(body)
            result = d.get("result", d.get("status", d.get("RCode", "?")))
        except:
            result = "HTML"
        print("  [%d] %s %s => %s" % (r.status_code, method, url.split("dfcfs.cn")[1][:40], result))
    except Exception as e:
        print("  [ERR] %s => %s" % (url.split("dfcfs.cn")[1][:40], str(e)[:60]))
