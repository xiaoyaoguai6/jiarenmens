# -*- coding: utf-8 -*-
"""最精简stealth：只注入桥接对象，不拦截任何东西"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.async_api import async_playwright

# 最精简stealth - 只注入桥接对象
MINIMAL_STEALTH = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
function mkBridge() {
    const stub = function() { return ''; };
    return new Proxy({}, {
        get: (t, k) => { if (k === 'toJSON' || k === Symbol.toPrimitive) return undefined; return t[k] || stub; },
        set: (t, k, v) => { t[k] = v; return true; }
    });
}
if (!window.emh5) window.emh5 = mkBridge();
if (!window.EMProjJs) window.EMProjJs = mkBridge();
if (!window.EMRead) window.EMRead = mkBridge();
if (!window.emjs) window.emjs = mkBridge();
"""

ZH_ID = "900023658"
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896}, user_agent=UA,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True, device_scale_factor=3,
        )
        await ctx.add_init_script(MINIMAL_STEALTH)
        page = await ctx.new_page()

        logs = []
        reqs = []
        page.on("console", lambda m: logs.append("[%s] %s" % (m.type, m.text[:200])))
        page.on("request", lambda r: reqs.append(r.url))

        print("加载页面...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=20000
        )
        await asyncio.sleep(15)

        body = await page.evaluate("document.body ? document.body.innerText : ''")
        html = await page.evaluate("document.body ? document.body.innerHTML : ''")
        print("innerText (%d字符): %s" % (len(body), body[:300]))
        print("\ninnerHTML (%d字符): %s" % (len(html), html[:500]))

        print("\n控制台日志:")
        for l in logs:
            print("  %s" % l)

        api_reqs = [u for u in reqs if "emdcspzhapi" in u or "rtV1" in u]
        print("\nAPI请求: %d" % len(api_reqs))
        for u in api_reqs:
            print("  %s" % u[:120])

        await browser.close()

asyncio.run(main())
