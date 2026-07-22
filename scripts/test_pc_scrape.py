# -*- coding: utf-8 -*-
"""Test PC page scraping for position data."""
import sys, io, requests, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

print("Fetching rank data...")
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
name = player["zhuheName"]
print("Player: %s (zh=%s, uid=%s)" % (name, zh_id, uid))

UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
url = "https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s&anchor=3" % uid

api_responses = []
print("Loading PC page: %s" % url)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA_PC, viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()

    def on_response(response):
        ct = response.headers.get("content-type", "")
        if "json" in ct:
            try:
                body = response.text()
                api_responses.append({"url": response.url, "status": response.status, "body": body[:5000]})
            except:
                pass

    page.on("response", on_response)

    try:
        page.goto(url, timeout=30000, wait_until="networkidle")
    except Exception as e:
        print("Page load: %s" % str(e)[:100])

    page.wait_for_timeout(3000)
    page_text = page.evaluate("document.body.innerText")
    print("\n=== Page text (first 2000) ===")
    print(page_text[:2000].encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    page.screenshot(path=r"D:\project\jiarenmens\data\debug\pc_scrape_test.png", full_page=True)
    print("\nScreenshot saved")
    browser.close()

print("\n=== JSON responses (%d) ===" % len(api_responses))
for r in api_responses:
    u = r["url"][:150]
    b = r["body"][:300].replace("\n", " ")
    print("  [%d] %s" % (r["status"], u))
    print("      %s" % b.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

print("\nDone!")
