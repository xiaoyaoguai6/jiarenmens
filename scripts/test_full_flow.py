# -*- coding: utf-8 -*-
"""在实际 H5 页面上测试路由拦截 + api001"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright
import requests as req_lib

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

session = req_lib.Session()
session.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

stats = {"routed": 0}

async def route_handler(route):
    stats["routed"] += 1
    url = route.request.url
    print("  [ROUTE #%d] %s %s" % (stats["routed"], route.request.method, url[:120]))
    try:
        if route.request.method == "GET":
            resp = session.get(url, timeout=15)
        else:
            resp = session.post(url, data=route.request.post_data, timeout=15)
        await route.fulfill(
            status=resp.status_code,
            headers={"Content-Type": "application/json"},
            body=resp.text,
        )
    except Exception as e:
        print("  [ROUTE] Error: %s" % e)
        await route.abort()

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, executable_path=CHROME,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896}, user_agent=UA,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True, device_scale_factor=3,
        )
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()

        await page.route("**/emdcspzhapi.dfcfs.cn/**", route_handler)

        console_msgs = []
        page.on("console", lambda m: console_msgs.append("[%s] %s" % (m.type, m.text[:200])))

        print("Loading H5 page...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(5)
        print("Routed during page load: %d" % stats["routed"])

        api001_str = await page.evaluate("window.emconfig && window.emconfig.Request && window.emconfig.Request.api001 ? window.emconfig.Request.api001.toString().slice(0, 100) : 'N/A'")
        print("api001: %s" % api001_str)

        stats["routed"] = 0
        print("\n=== Calling api001 ===")
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.Request.api001({
                url: "rtV1",
                type: "rt_get_info",
                data: {zh: "900113132", appVer: "9001000"},
                success: function(t) { resolve({ok: true, len: t.length, preview: t.slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 10000);
        })"""), timeout=15)
        print("Result: %s" % result)
        print("Routed during api001: %d" % stats["routed"])

        body = await page.evaluate("document.body ? document.body.innerText : ''")
        print("\nPage text (%d): %s" % (len(body), body[:500]))

        await browser.close()

asyncio.run(main())
