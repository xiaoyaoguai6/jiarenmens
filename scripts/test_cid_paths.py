# -*- coding: utf-8 -*-
"""用正确的cid测试emstockdiag网关的所有可能路径"""
import sys, io, json, requests, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

ZH = "900023658"
CID = "9f69c1bcff839a3202625794b00c75e3"
APPKEY = "a8157f5ef970edda2c103e192b6dc3e5"
PAGE_URL = "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH

def test_gateway(path, parm_dict):
    body = {
        "path": path,
        "parm": json.dumps(parm_dict),
        "header": {"appkey": APPKEY, "Referer": "http://www.eastmoney.com", "ut": "", "ct": ""},
        "track": "sys_%d" % int(time.time() * 1000),
        "pageUrl": PAGE_URL,
    }
    try:
        r = s.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData", json=body, timeout=10)
        d = r.json()
        rcode = d.get("RCode", "?")
        rdata = d.get("RData", "")
        if rdata:
            try:
                inner = json.loads(rdata)
                return rcode, inner
            except:
                return rcode, rdata
        return rcode, None
    except Exception as e:
        return "ERR", str(e)

# 1. 用cid测试所有v4/mobileadapter路径
print("=== v4/mobileadapter 路径 (cid=%s) ===" % CID[:20])
paths = [
    "v4/mobileadapter/gszcount",
    "v4/mobileadapter/positionlist",
    "v4/mobileadapter/tradelist",
    "v4/mobileadapter/detail",
    "v4/mobileadapter/info",
    "v4/mobileadapter/stocklist",
    "v4/mobileadapter/hold",
    "v4/mobileadapter/holding",
    "v4/mobileadapter/summary",
    "v4/mobileadapter/overview",
    "v4/mobileadapter/asset",
    "v4/mobileadapter/fund",
    "v4/mobileadapter/history",
    "v4/mobileadapter/record",
    "v4/mobileadapter/rebalance",
    "v4/mobileadapter/combination",
    "v4/mobileadapter/getPosition",
    "v4/mobileadapter/getTrade",
    "v4/mobileadapter/getDetail",
    "v4/mobileadapter/getInfo",
    "v4/mobileadapter/getStock",
    "v4/mobileadapter/getHold",
    "v4/mobileadapter/query-privacy-config",
]

parm = {"cid": CID, "zh": ZH}
for path in paths:
    rcode, data = test_gateway(path, parm)
    if rcode == 200 and data and isinstance(data, dict):
        state = data.get("state", "?")
        msg = data.get("message", "")
        d = data.get("data")
        if state == 0 and d:
            print("  ** %s => state=0 data=%s" % (path, json.dumps(d, ensure_ascii=False)[:200]))
        elif state != -4:
            print("     %s => state=%s msg=%s" % (path, state, msg[:60]))
    elif rcode != 10:
        print("     %s => RCode=%s" % (path, rcode))

# 2. 用不同参数测试rspThird handlers
print("\n=== rspThird handlers (多种参数) ===")
handlers = [
    "rspThird/community/positionlist_handler",
    "rspThird/community/tradelist_handler",
    "rspThird/community/detail_handler",
    "rspThird/community/stocklist_handler",
    "rspThird/community/info_handler",
    "rspThird/community/post_header_yield_handler",
    "rspThird/shipan/positionlist_handler",
    "rspThird/shipan/tradelist_handler",
    "rspThird/shipan/detail_handler",
]

parm_sets = [
    {"cid": CID, "zh": ZH},
    {"cid": CID},
    {"zh": ZH, "cid": CID, "appVer": "9001000"},
    {"zjzh": ZH, "cid": CID},
    {"combinationId": ZH, "cid": CID},
    {"userId": "2012094520785316", "cid": CID},
]

for handler in handlers:
    name = handler.split("/")[-1]
    for ps in parm_sets:
        rcode, data = test_gateway(handler, ps)
        if rcode == 200 and data and isinstance(data, dict):
            state = data.get("state", "?")
            if state == 0:
                print("  ** %s parm=%s => state=0 data=%s" % (name, json.dumps(ps)[:40], json.dumps(data.get("data"), ensure_ascii=False)[:200]))
        elif rcode not in [10, "ERR"]:
            print("     %s parm=%s => RCode=%s" % (name, json.dumps(ps)[:40], rcode))

# 3. 测试v3/v2版本
print("\n=== v3/v2 版本 ===")
for ver in ["v3", "v2", "v1"]:
    for sub in ["mobileadapter/gszcount", "mobileadapter/positionlist", "mobileadapter/tradelist"]:
        path = "%s/%s" % (ver, sub)
        rcode, data = test_gateway(path, {"cid": CID, "zh": ZH})
        if rcode == 200 and data and isinstance(data, dict):
            state = data.get("state", "?")
            if state == 0:
                print("  ** %s => state=0 data=%s" % (path, json.dumps(data.get("data"), ensure_ascii=False)[:200]))
            elif state != -4:
                print("     %s => state=%s" % (path, state))
