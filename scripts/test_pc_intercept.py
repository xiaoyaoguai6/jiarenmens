# -*- coding: utf-8 -*-
"""Intercept PC page to capture full API request details."""
import sys, io, requests, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6)",
    "Referer": "https://groupwap.eastmoney.com",
})

# Get player with uid
r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params={
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
print("Player: %s (zh=%s, uid=%s)" % (player["zhuheName"], zh_id, uid))

UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
url = "https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s&anchor=3" % uid

captured = []
print("Loading PC page...")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA_PC, viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()

    def on_request(request):
        req_url = request.url
        if any(k in req_url for k in ["Tran/", "apistock", "post_header_yield", "community", "spzhapi", "emstockdiag"]):
            captured.append({
                "url": req_url,
                "method": request.method,
                "post_data": request.post_data,
                "headers": dict(request.headers) if request.headers else {},
            })

    def on_response(response):
        req_url = response.url
        if any(k in req_url for k in ["Tran/", "apistock", "post_header_yield", "community", "spzhapi", "emstockdiag"]):
            try:
                body = response.text()
                for c in captured:
                    if c["url"] == req_url and "resp_body" not in c:
                        c["resp_body"] = body[:10000]
                        c["resp_status"] = response.status
                        c["resp_headers"] = dict(response.headers) if response.headers else {}
                        break
            except:
                pass

    page.on("request", on_request)
    page.on("response", on_response)

    try:
        page.goto(url, timeout=30000, wait_until="networkidle")
    except Exception as e:
        print("Load: %s" % str(e)[:100])

    page.wait_for_timeout(5000)
    browser.close()

print("\n=== Captured API calls (%d) ===" % len(captured))
for c in captured:
    print("\n--- %s %s ---" % (c["method"], c["url"]))
    if c.get("post_data"):
        print("  POST: %s" % c["post_data"][:500])
    print("  Status: %s" % c.get("resp_status", "?"))
    print("  Body: %s" % str(c.get("resp_body", ""))[:1000])
    # Show relevant headers
    for hk in ["referer", "origin", "content-type", "cookie"]:
        if hk in c.get("headers", {}):
            print("  Header %s: %s" % (hk, c["headers"][hk][:200]))

print("\nDone!")
