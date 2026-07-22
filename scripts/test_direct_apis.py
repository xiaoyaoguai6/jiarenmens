# -*- coding: utf-8 -*-
"""Test calling discovered APIs directly."""
import sys, io, requests, json, hashlib, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://emcreative.eastmoney.com/",
    "Content-Type": "application/json",
})

# Get a player
rs = requests.Session()
rs.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://groupwap.eastmoney.com"})
r = rs.get("https://emdcspzhapi.dfcfs.cn/rtV1", params={
    "type": "rt_get_rank", "rankType": "10004", "recIdx": 0, "recCnt": 5, "rankid": 0, "appVer": "9001000"
}, timeout=15)
data = r.json()["data"]
player = None
for p in data:
    if p.get("userid"):
        player = p
        break

zh_id = player["zjzh"]
uid = player["userid"]
name = player["zhuheName"]
print("Player: %s (zh=%s, uid=%s)" % (name, zh_id, uid))

# Check if cid is MD5 of uid or zh_id
print("\n=== CID analysis ===")
uid_md5 = hashlib.md5(uid.encode()).hexdigest()
zh_md5 = hashlib.md5(zh_id.encode()).hexdigest()
print("MD5(uid): %s" % uid_md5)
print("MD5(zh_id): %s" % zh_md5)
captured_cid = "9f69c1bcff839a3202625794b00c75e3"
print("Captured cid: %s" % captured_cid)
print("Match uid? %s" % (uid_md5 == captured_cid))
print("Match zh_id? %s" % (zh_md5 == captured_cid))

# Test 1: post_header_yield_handler - direct call
print("\n=== Test 1: post_header_yield_handler ===")
for test_uid in [uid, "2012094520785316", "5887346444580316"]:
    try:
        r = s.post("https://spzhapi.dfcfs.cn/rspThird/community/post_header_yield_handler",
                    json={
                        "args": {"userId": test_uid},
                        "client": "wap",
                        "clientType": "cfw",
                        "clientVersion": "9001",
                        "timestamp": int(time.time() * 1000),
                    }, timeout=10)
        d = r.json()
        print("  uid=%s => %s" % (test_uid, json.dumps(d, ensure_ascii=False)[:300]))
    except Exception as e:
        print("  uid=%s => ERROR: %s" % (test_uid, e))

# Test 2: emstockdiag GetData gateway - try different path values
print("\n=== Test 2: emstockdiag GetData gateway ===")
appkey = "a8157f5ef970edda2c103e192b6dc3e5"
paths_to_try = [
    "v4/mobileadapter/gszcount",
    "v4/mobileadapter/position",
    "v4/mobileadapter/trade",
    "v4/mobileadapter/detail",
    "v4/mobileadapter/stock",
    "v4/mobileadapter/hold",
    "v4/mobileadapter/holding",
    "v4/mobileadapter/portfolio",
    "v4/mobileadapter/asset",
    "v4/mobileadapter/summary",
    "v4/mobileadapter/fund",
    "v4/mobileadapter/history",
    "v4/mobileadapter/record",
    "v4/mobileadapter/rebalance",
    "v4/mobileadapter/combination",
    "v4/mobileadapter/info",
    "v4/mobileadapter/zjzh",
    "v4/mobileadapter/zjzh_position",
    "v4/mobileadapter/zjzh_change",
    "v3/mobileadapter/gszcount",
    "v3/mobileadapter/position",
    "v3/mobileadapter/trade",
    "v3/mobileadapter/detail",
    "v3/mobileadapter/stock",
    "v3/mobileadapter/hold",
    "v3/mobileadapter/holding",
    "v2/mobileadapter/position",
    "v2/mobileadapter/trade",
    "v2/mobileadapter/detail",
    "v1/mobileadapter/position",
    "v1/mobileadapter/trade",
    "v1/mobileadapter/detail",
    "v4/zuhe/position",
    "v4/zuhe/trade",
    "v4/zuhe/detail",
    "v4/zuhe/stock",
    "v4/zuhe/hold",
    "v4/shipan/position",
    "v4/shipan/trade",
    "v4/shipan/detail",
    "v4/shipan/stock",
    "v4/shipan/hold",
    "v4/community/position",
    "v4/community/trade",
    "v4/community/detail",
    "v4/community/stock",
    "v4/community/hold",
    "v4/fund/position",
    "v4/fund/trade",
    "v4/fund/detail",
    "v4/fund/stock",
    "v4/fund/hold",
    "v4/fortune/position",
    "v4/fortune/trade",
    "v4/fortune/detail",
    "v4/fortune/stock",
    "v4/fortune/hold",
    "v4/real/position",
    "v4/real/trade",
    "v4/real/detail",
    "v4/real/stock",
    "v4/real/hold",
    "v4/real/holding",
    "v4/real/summary",
    "v4/real/info",
    "v4/real/portfolio",
    "v4/real/asset",
    "v4/real/fund",
    "v4/real/history",
    "v4/real/record",
    "v4/real/rebalance",
    "v4/real/zjzh",
    "v4/real/zjzh_position",
    "v4/real/zjzh_change",
    "v4/real/zjzh_info",
    "v4/real/zjzh_detail",
    "v4/real/zjzh_stock",
    "v4/real/zjzh_hold",
    "v4/real/zjzh_holding",
    "v4/real/zjzh_portfolio",
    "v4/real/zjzh_trade",
]

page_url = "https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s&anchor=3" % uid
found = []
for path in paths_to_try:
    try:
        body = {
            "path": path,
            "parm": json.dumps({"cid": captured_cid}),
            "header": {
                "appkey": appkey,
                "Referer": "http://www.eastmoney.com",
                "ut": "", "ct": "", "MyFavorVer": "",
            },
            "track": "sys_%d" % int(time.time() * 1000),
            "pageUrl": page_url,
        }
        r = s.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData",
                    json=body, timeout=10)
        d = r.json()
        rdata = d.get("RData", "")
        rcode = d.get("RCode", 0)
        if rcode == 200 and rdata:
            inner = json.loads(rdata)
            state = inner.get("state", -1)
            msg = inner.get("message", "")
            data = inner.get("data")
            if state == 0 and data:
                print("  ** %s => state=0, data=%s" % (path, json.dumps(data, ensure_ascii=False)[:300]))
                found.append(path)
            elif state != -1:
                print("     %s => state=%s, msg=%s" % (path, state, msg))
    except Exception as e:
        pass

if not found:
    print("  No paths returned data (except gszcount)")

print("\n=== Found working paths ===")
for f in found:
    print("  %s" % f)

# Test 3: Try calling post_header_yield_handler for multiple players from rank
print("\n=== Test 3: post_header_yield_handler for multiple players ===")
for p in data[:5]:
    test_uid = p.get("userid", "")
    test_zh = p.get("zjzh", "")
    if not test_uid:
        print("  zh=%s: no uid" % test_zh)
        continue
    try:
        r = s.post("https://spzhapi.dfcfs.cn/rspThird/community/post_header_yield_handler",
                    json={
                        "args": {"userId": test_uid},
                        "client": "wap",
                        "clientType": "cfw",
                        "clientVersion": "9001",
                        "timestamp": int(time.time() * 1000),
                    }, timeout=10)
        d = r.json()
        print("  zh=%s uid=%s => %s" % (test_zh, test_uid, json.dumps(d.get("data", {}), ensure_ascii=False)[:200]))
    except Exception as e:
        print("  zh=%s => ERROR: %s" % (test_zh, e))

print("\nDone!")
