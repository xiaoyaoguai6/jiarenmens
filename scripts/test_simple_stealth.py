# -*- coding: utf-8 -*-
"""使用 GitHub 仓库的简单 stealth 脚本测试"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

# GitHub 仓库的简单 stealth 脚本
SIMPLE_STEALTH = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
const __origQuery = window.navigator.permissions && window.navigator.permissions.query;
if (__origQuery) {
    window.navigator.permissions.query = (parameters) => (
        parameters && parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : __origQuery(parameters)
    );
}
function __mkBridge() {
    const noop = function() {};
    const stub = function() { return ''; };
    return new Proxy({}, {
        get: (t, k) => {
            if (k === 'toJSON' || k === Symbol.toPrimitive) return undefined;
            return t[k] || stub;
        },
        set: (t, k, v) => { t[k] = v; return true; }
    });
}
if (!window.emh5) window.emh5 = __mkBridge();
if (!window.EMProjJs) window.EMProjJs = __mkBridge();
if (!window.EMRead) window.EMRead = __mkBridge();
if (!window.emjs) window.emjs = __mkBridge();
"""

CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

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
        await ctx.add_init_script(SIMPLE_STEALTH)
        page = await ctx.new_page()

        all_reqs = []
        all_resps = []
        errors = []
        console = []

        page.on("request", lambda r: all_reqs.append({"url": r.url, "method": r.method}))
        page.on("response", lambda r: all_resps.append({"url": r.url, "status": r.status}))
        page.on("pageerror", lambda e: errors.append(str(e)[:300]))
        page.on("console", lambda m: console.append("[%s] %s" % (m.type, m.text[:300])))

        print("Loading detail page...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(10)

        body = await page.evaluate("document.body ? document.body.innerText : ''")
        print("Body text (%d chars):" % len(body))
        print(body[:800])

        # 检查 emconfig
        check = await page.evaluate("""() => ({
            hasEmconfig: !!window.emconfig,
            hasRequest: !!(window.emconfig && window.emconfig.Request),
            hasApi001: !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api001),
            api001Type: typeof (window.emconfig && window.emconfig.Request && window.emconfig.Request.api001),
        })""")
        print("\n=== emconfig ===")
        for k, v in check.items():
            print("  %s: %s" % (k, v))

        # API 请求
        api_reqs = [r for r in all_reqs if "emdcspzhapi" in r["url"] or "rtV1" in r["url"]]
        print("\n=== API requests ===")
        for r in api_reqs:
            print("  %s %s" % (r["method"], r["url"][:150]))

        # 错误
        print("\n=== Errors ===")
        for e in errors:
            print("  %s" % e)

        # Console
        print("\n=== Console ===")
        for m in console[:20]:
            print("  %s" % m)

        # 截图
        await page.screenshot(path=r"D:\project\jiarenmens\data\debug\simple_stealth.png", full_page=True)

        await browser.close()

asyncio.run(main())
