# -*- coding: utf-8 -*-
"""测试路由拦截是否工作"""
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

async def route_handler(route):
    url = route.request.url
    print("  [ROUTE] Intercepted: %s" % url[:100])
    try:
        if route.request.method == "GET":
            resp = session.get(url, timeout=15)
        else:
            resp = session.post(url, data=route.request.post_data, timeout=15)
        print("  [ROUTE] Response: %d, len=%d" % (resp.status_code, len(resp.text)))
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

        # 尝试不同的路由模式
        print("=== Setting up routes ===")
        await page.route("**/emdcspzhapi.dfcfs.cn/**", route_handler)
        print("Route set: **/emdcspzhapi.dfcfs.cn/**")

        # 先测试页面内的直接 fetch
        print("\n=== Testing direct fetch from page ===")
        await page.goto("about:blank")
        result = await page.evaluate("""() => new Promise((resolve) => {
            fetch("https://emdcspzhapi.dfcfs.cn/rtV1?type=rt_get_rank&rankType=10004&recIdx=0&recCnt=1&rankid=0&appVer=9001000")
                .then(r => r.text().then(t => resolve({ok: true, status: r.status, len: t.length})))
                .catch(e => resolve({error: e.message}));
            setTimeout(() => resolve({timeout: true}), 10000);
        })""")
        print("Result: %s" % result)

        await browser.close()

asyncio.run(main())
