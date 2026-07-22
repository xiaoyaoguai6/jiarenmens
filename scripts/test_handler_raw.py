# -*- coding: utf-8 -*-
"""Test handler APIs with raw response output."""
import sys, io, requests, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ZH_ID = "900013608"
UID = "2012094520785316"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://emcreative.eastmoney.com/",
    "Content-Type": "application/json",
    "Origin": "https://emcreative.eastmoney.com",
})

handlers = [
    "rspThird/community/positionlist_handler",
    "rspThird/community/tradelist_handler",
    "rspThird/community/detail_handler",
]

for handler in handlers:
    name = handler.split("/")[-1]
    for label, args in [("userId", {"userId": UID}), ("combinationId", {"combinationId": ZH_ID})]:
        body = {
            "args": args,
            "client": "wap",
            "clientType": "cfw",
            "clientVersion": "9001",
            "timestamp": int(time.time() * 1000),
        }
        url = "https://spzhapi.dfcfs.cn/%s" % handler
        try:
            r = s.post(url, json=body, timeout=10)
            print("\n%s (%s) => %d" % (name, label, r.status_code))
            print("  Content-Type: %s" % r.headers.get("content-type", ""))
            text = r.text[:1000]
            print("  Body: %s" % text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
        except Exception as e:
            print("\n%s (%s) => ERROR: %s" % (name, label, e))

# Also try GET requests
print("\n\n=== Trying GET requests ===")
for handler in handlers:
    name = handler.split("/")[-1]
    url = "https://spzhapi.dfcfs.cn/%s" % handler
    for label, params in [("userId", {"userId": UID}), ("combinationId", {"combinationId": ZH_ID}), ("zh", {"zh": ZH_ID})]:
        try:
            r = s.get(url, params=params, timeout=10)
            print("\nGET %s (%s) => %d" % (name, label, r.status_code))
            text = r.text[:500]
            print("  Body: %s" % text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
        except Exception as e:
            print("\nGET %s (%s) => ERROR: %s" % (name, label, e))

# Try the yield handler that we KNOW works from PC page
print("\n\n=== Yield handler (known working) ===")
body = {
    "args": {"userId": UID},
    "client": "wap",
    "clientType": "cfw",
    "clientVersion": "9001",
    "timestamp": int(time.time() * 1000),
}
try:
    r = s.post("https://spzhapi.dfcfs.cn/rspThird/community/post_header_yield_handler",
               json=body, timeout=10)
    print("Status: %d" % r.status_code)
    print("Body: %s" % r.text[:500].encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
except Exception as e:
    print("ERROR: %s" % e)

print("\nDone!")
