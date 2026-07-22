# -*- coding: utf-8 -*-
"""Test rspThird/community/positionlist_handler and tradelist_handler."""
import sys, io, requests, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ZH_ID = "900013608"
UID = "2012094520785316"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://emcreative.eastmoney.com/",
    "Content-Type": "application/json",
})

base_args_sets = [
    # Try with userId
    {"args": {"userId": UID}, "client": "wap", "clientType": "cfw", "clientVersion": "9001", "timestamp": 0},
    # Try with combinationId
    {"args": {"combinationId": ZH_ID}, "client": "wap", "clientType": "cfw", "clientVersion": "9001", "timestamp": 0},
    # Try with both
    {"args": {"userId": UID, "combinationId": ZH_ID}, "client": "wap", "clientType": "cfw", "clientVersion": "9001", "timestamp": 0},
    # Try with zh
    {"args": {"zh": ZH_ID}, "client": "wap", "clientType": "cfw", "clientVersion": "9001", "timestamp": 0},
    # Try with zjzh
    {"args": {"zjzh": ZH_ID}, "client": "wap", "clientType": "cfw", "clientVersion": "9001", "timestamp": 0},
]

handlers = [
    "rspThird/community/positionlist_handler",
    "rspThird/community/tradelist_handler",
    "rspThird/community/detail_handler",
    "rspThird/community/stocklist_handler",
    "rspThird/community/info_handler",
]

for handler in handlers:
    print("\n=== %s ===" % handler.split("/")[-1])
    for i, args_set in enumerate(base_args_sets):
        args_set["timestamp"] = int(time.time() * 1000)
        try:
            r = s.post("https://spzhapi.dfcfs.cn/%s" % handler,
                       json=args_set, timeout=10)
            d = r.json()
            code = d.get("code", "?")
            msg = str(d.get("message", ""))[:80]
            data = d.get("data")
            if code == 0 and data:
                data_str = json.dumps(data, ensure_ascii=False)[:500]
                print("  ** args[%d] code=%s => %s" % (i, code, data_str))
            else:
                print("     args[%d] code=%s msg=%s" % (i, code, msg))
        except Exception as e:
            print("     args[%d] ERROR: %s" % (i, str(e)[:80]))

print("\nDone!")
