# -*- coding: utf-8 -*-
"""
方案：用 Playwright route() 拦截跨域请求，代理到 Python requests。
这样页面的 fetch 可以正常工作，绕过 CORS 限制。
"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright
import requests as req

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900113132"
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

# Python requests session for proxying
session = req.Session()
session.headers.update({
    "User-Agent": UA,
    "Referer": "https://groupwap.eastmoney.com",
})

async def route_handler(route):
    """拦截对 emdcspzhapi.dfcfs.cn 的请求，用 Python requests 代理"""
    request = route.request
    url = request.url
    method = request.method

    try:
        if method == "GET":
            resp = session.get(url, timeout=15)
        else:
            post_data = request.post_data
            headers = {}
            for h in request.headers:
                if h.lower() in ["content-type"]:
                    headers[h] = request.headers[h]
            resp = session.post(url, data=post_data, headers=headers, timeout=15)

        await route.fulfill(
            status=resp.status_code,
            headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            body=resp.text,
        )
    except Exception as e:
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

        # 拦截 emdcspzhapi 的请求
        await page.route("**/*emdcspzhapi*", route_handler)

        reqs = []
        page.on("request", lambda r: reqs.append(r.url))

        print("Loading page...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(5)

        print("Requests during page load: %d" % len(reqs))
        for u in reqs:
            if "emdcspzhapi" in u:
                print("  PROXIED: %s" % u[:150])

        # 手动调用 api001
        reqs.clear()
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
        print("  Result: %s" % result)

        print("\nRequests during api001: %d" % len(reqs))
        for u in reqs:
            if "emdcspzhapi" in u:
                print("  PROXIED: %s" % u[:150])

        # 检查页面内容
        body = await page.evaluate("document.body ? document.body.innerText : ''")
        print("\n=== Page text ===")
        print(body[:500])

        await browser.close()

asyncio.run(main())
