# -*- coding: utf-8 -*-
"""Deep explore: click into combos on PC page, intercept ALL requests."""
import sys, io, json, time, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
import requests

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://groupwap.eastmoney.com"})
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
base_url = "https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s" % uid

all_captured = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA_PC, viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()

    def capture(resp):
        url = resp.url
        ct = resp.headers.get("content-type", "")
        # Capture ALL non-static requests
        if any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".gif", ".woff", ".ttf", ".svg"]):
            return
        if resp.status != 200:
            return
        try:
            body = resp.text()
        except:
            return
        entry = {"url": url, "ct": ct, "body": body[:3000], "status": resp.status}
        all_captured.append(entry)

    page.on("response", capture)

    # Load the person page (default tab - posts/articles)
    print("\n[1] Loading person page (default tab)...")
    try:
        page.goto(base_url, timeout=30000, wait_until="networkidle")
    except Exception as e:
        print("  Load: %s" % str(e)[:80])
    page.wait_for_timeout(3000)

    # Click on "combo" tab (anchor=3)
    print("\n[2] Clicking combo tab...")
    all_captured.clear()
    try:
        combo_tab = page.locator("text=combo").first
        if combo_tab.is_visible():
            combo_tab.click()
            page.wait_for_timeout(3000)
        else:
            # Try anchor=3 URL directly
            page.goto(base_url + "&anchor=3", timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(3000)
    except Exception as e:
        print("  Tab click: %s" % str(e)[:80])

    # Get page text to see what's visible
    page_text = page.evaluate("document.body.innerText")
    print("  Page text (first 500): %s" % page_text[:500].encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    # Find all links on the page
    print("\n[3] Finding links...")
    links = page.evaluate("""() => {
        const links = [];
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || '').trim().substring(0, 100);
            if (href && (href.includes('combination') || href.includes('zuhe') || href.includes('detail') || href.includes('combo') || href.includes('person'))) {
                links.push({href: href, text: text});
            }
        });
        return links;
    }""")
    for l in links[:20]:
        print("  Link: %s => %s" % (l["text"][:50], l["href"][:100]))

    # Find all clickable elements with combo/position text
    print("\n[4] Finding clickable elements...")
    elements = page.evaluate("""() => {
        const results = [];
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const text = (el.innerText || '').trim();
            const tag = el.tagName;
            if (text.length > 0 && text.length < 50 && /(?:combo|position|stock|combo|detail|\\d{6})/.test(text)) {
                results.push({tag: tag, text: text.substring(0, 80), cls: (el.className || '').substring(0, 50)});
            }
        }
        return results.slice(0, 30);
    }""")
    for e in elements:
        print("  %s .%s: %s" % (e["tag"], e["cls"][:30], e["text"][:80].encode("utf-8", errors="replace").decode("utf-8", errors="replace")))

    # Now try the combo page directly
    print("\n[5] Loading combo page (anchor=3)...")
    all_captured.clear()
    try:
        page.goto(base_url + "&anchor=3", timeout=30000, wait_until="networkidle")
    except Exception as e:
        print("  Load: %s" % str(e)[:80])
    page.wait_for_timeout(5000)

    # Get full page text
    combo_text = page.evaluate("document.body.innerText")
    print("  Combo page text (first 1000):")
    print("  %s" % combo_text[:1000].encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    # Try to find and click on a combo link
    print("\n[6] Looking for combo links to click...")
    combo_links = page.evaluate("""() => {
        const results = [];
        const all = document.querySelectorAll('a, div, span');
        for (const el of all) {
            const text = (el.innerText || '').trim();
            const href = el.href || '';
            if (text.length > 0 && text.length < 100 && (text.includes('combo') || text.includes('combo') || /combo\\d/.test(text))) {
                results.push({tag: el.tagName, text: text.substring(0, 80), href: href.substring(0, 100)});
            }
        }
        return results.slice(0, 20);
    }""")
    for l in combo_links:
        print("  %s: %s => %s" % (l["tag"], l["text"][:50].encode("utf-8", errors="replace").decode("utf-8", errors="replace"), l["href"][:100]))

    # Screenshot
    page.screenshot(path=r"D:\project\jiarenmens\data\debug\pc_combo_page.png", full_page=True)
    print("\n  Screenshot saved")

    browser.close()

# Show captured API responses
print("\n=== Captured responses (%d) ===" % len(all_captured))
for c in all_captured:
    url = c["url"][:150]
    body = c["body"][:300].replace("\n", " ")
    if any(k in url for k in ["api", "handler", "tran", "getData", "combo", "position", "stock", "fortune"]):
        print("\n  ** %s" % url)
        print("     Body: %s" % body.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

print("\nDone!")
