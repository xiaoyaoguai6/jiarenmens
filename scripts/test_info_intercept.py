# -*- coding: utf-8 -*-
"""Load H5 info/detail/change pages with Playwright, intercept ALL API calls."""
import sys, io, json, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

ZH_ID = "900113132"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

pages_to_test = [
    ("info", "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH_ID),
    ("detail", "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID),
    ("change", "https://groupwap.eastmoney.com/group/reality/change.html?zh=%s" % ZH_ID),
]

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, viewport={"width": 414, "height": 896})

    for name, url in pages_to_test:
        print("\n=== %s: %s ===" % (name, url))
        all_reqs = []
        all_resps = []
        page = ctx.new_page()

        def on_req(req):
            all_reqs.append({"url": req.url, "method": req.method, "post": req.post_data})

        def on_resp(resp):
            ct = resp.headers.get("content-type", "")
            if any(k in ct for k in ["json", "javascript", "text/plain"]):
                try:
                    body = resp.text()
                    all_resps.append({"url": resp.url, "status": resp.status, "body": body[:5000]})
                except:
                    pass

        page.on("request", on_req)
        page.on("response", on_resp)

        try:
            page.goto(url, timeout=30000, wait_until="networkidle")
        except Exception as e:
            print("  Load: %s" % str(e)[:100])
        page.wait_for_timeout(5000)

        # Show page title and body text
        title = page.title()
        body_text = page.evaluate("document.body.innerText")[:500]
        print("  Title: %s" % title.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
        print("  Body: %s" % body_text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

        # Show non-static requests
        print("  Requests (%d):" % len(all_reqs))
        for r in all_reqs:
            u = r["url"]
            if not any(ext in u for ext in [".js", ".css", ".png", ".jpg", ".gif", ".woff", ".ttf", ".svg", ".ico"]):
                print("    %s %s" % (r["method"], u[:150]))

        # Show API responses
        print("  API responses (%d):" % len(all_resps))
        for r in all_resps:
            u = r["url"][:150]
            b = r["body"][:300].encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print("    [%d] %s" % (r["status"], u))
            print("      %s" % b)

        # Screenshot
        page.screenshot(path="D:\\project\\jiarenmens\\data\\debug\\%s_page.png" % name, full_page=True)
        print("  Screenshot saved")

        # Save HTML
        html = page.content()
        with open("D:\\project\\jiarenmens\\data\\debug\\%s_full.html" % name, "w", encoding="utf-8") as f:
            f.write(html)
        print("  HTML saved")

        page.close()

    browser.close()

print("\nDone!")
