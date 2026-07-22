# -*- coding: utf-8 -*-
"""深入检查 H5 页面的 JS 执行情况"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900113132"
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
URL = "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID

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

        all_reqs = []
        all_resps = []
        errors = []
        console = []

        page.on("request", lambda r: all_reqs.append({"url": r.url, "method": r.method}))
        page.on("response", lambda r: all_resps.append({"url": r.url, "status": r.status, "ct": r.headers.get("content-type", "")}))
        page.on("pageerror", lambda e: errors.append(str(e)[:300]))
        page.on("console", lambda m: console.append("[%s] %s" % (m.type, m.text[:300])))

        resp = await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(10)

        print("=== HTML HEAD (script tags) ===")
        scripts = await page.evaluate("""
            () => Array.from(document.querySelectorAll('script')).map(s => ({
                src: s.src || '(inline)',
                text: s.text ? s.text.slice(0, 200) : ''
            }))
        """)
        for s in scripts:
            if s["src"] != "(inline)":
                print("  SRC: %s" % s["src"][:150])
            elif s["text"]:
                print("  INLINE: %s" % s["text"][:150])

        print("\n=== ALL JS/CSS loaded ===")
        js_resps = [r for r in all_resps if ".js" in r["url"] or ".css" in r["url"]]
        for r in js_resps:
            print("  [%d] %s" % (r["status"], r["url"][:150]))

        print("\n=== ALL requests ===")
        for r in all_reqs:
            if not any(ext in r["url"] for ext in [".png", ".jpg", ".gif", ".woff", ".ttf", ".svg", ".ico"]):
                print("  %s %s" % (r["method"], r["url"][:150]))

        print("\n=== Console msgs ===")
        for m in console:
            print("  %s" % m)

        print("\n=== Page errors ===")
        for e in errors:
            print("  %s" % e)

        # 检查 emconfig 是否存在
        emconfig_check = await page.evaluate("""
            () => {
                return {
                    hasEmconfig: !!window.emconfig,
                    hasRequest: !!(window.emconfig && window.emconfig.Request),
                    hasApi001: !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api001),
                    hasApi003: !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api003),
                    hasEmDialog: !!window.emDialog,
                    hasEmRuntime: !!window.emRuntime,
                    inApp: window.emRuntime && window.emRuntime.InApp,
                };
            }
        """)
        print("\n=== emconfig check ===")
        for k, v in emconfig_check.items():
            print("  %s: %s" % (k, v))

        # 手动尝试调用 api001
        print("\n=== Manual api001 call ===")
        result = await page.evaluate("""
            () => new Promise((resolve) => {
                if (!window.emconfig || !window.emconfig.Request || !window.emconfig.Request.api001) {
                    resolve({error: "api001 not available"});
                    return;
                }
                window.emconfig.Request.api001({
                    url: "rtV1",
                    type: "rt_get_info",
                    data: {zh: "%s", appVer: "9001000"},
                    success: function(t) { resolve({ok: true, data: t.slice(0, 500)}); },
                    error: function(e) { resolve({error: String(e)}); }
                });
            })
        """ % ZH_ID)
        print("  Result: %s" % result)

        await browser.close()

asyncio.run(main())
