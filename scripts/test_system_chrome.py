# -*- coding: utf-8 -*-
"""用系统Chrome测试H5页面"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900023658"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

async def main():
    async with async_playwright() as pw:
        # 用系统Chrome而不是Playwright Chromium
        browser = await pw.chromium.launch(
            headless=True,
            channel="chrome",  # 使用系统Chrome
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896}, user_agent=UA,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True, device_scale_factor=3,
        )
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()

        reqs = []
        page.on("request", lambda r: reqs.append(r.url))

        print("用系统Chrome加载页面...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=20000
        )
        await asyncio.sleep(10)

        body = await page.evaluate("document.body ? document.body.innerText : ''")
        print("页面文本 (%d字符):" % len(body))
        print(body[:500])

        api_reqs = [u for u in reqs if "emdcspzhapi" in u or "eastmoney" in u]
        print("\nAPI请求: %d" % len(api_reqs))
        for u in api_reqs[:10]:
            print("  %s" % u[:120])

        await browser.close()

asyncio.run(main())
