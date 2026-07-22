# -*- coding: utf-8 -*-
"""快速检查 H5 页面 JS 加载情况"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900113132"
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
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()

        all_urls = []
        page.on("request", lambda r: all_urls.append(r.url))

        print("Loading page...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        print("Page loaded, waiting 5s...")
        await asyncio.sleep(5)

        # 列出所有加载的资源
        print("\n=== Loaded resources (%d) ===" % len(all_urls))
        for u in all_urls:
            if ".js" in u or "api" in u.lower():
                print("  %s" % u[:150])

        # 检查关键全局变量
        check = await page.evaluate("""() => ({
            hasEmconfig: !!window.emconfig,
            hasRequest: !!(window.emconfig && window.emconfig.Request),
            hasApi001: !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api001),
            hasEmDialog: !!window.emDialog,
            hasEmRuntime: !!window.emRuntime,
            inApp: window.emRuntime && window.emRuntime.InApp,
            bodyLen: document.body ? document.body.innerHTML.length : 0,
        })""")
        print("\n=== Globals ===")
        for k, v in check.items():
            print("  %s: %s" % (k, v))

        # 尝试手动调用 api001
        if check["hasApi001"]:
            print("\n=== Manual api001 call ===")
            try:
                result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
                    window.emconfig.Request.api001({
                        url: "rtV1",
                        type: "rt_get_info",
                        data: {zh: "900113132", appVer: "9001000"},
                        success: function(t) { resolve({ok: true, len: t.length, data: t.slice(0, 300)}); },
                        error: function(e) { resolve({error: String(e)}); }
                    });
                    setTimeout(() => resolve({timeout: true}), 10000);
                })"""), timeout=15)
                print("  Result: %s" % result)
            except Exception as e:
                print("  Error: %s" % e)

        await browser.close()

asyncio.run(main())
