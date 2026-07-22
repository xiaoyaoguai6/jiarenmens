# -*- coding: utf-8 -*-
"""
验证 H5 页面能否正确加载持仓数据。
使用已有的 chromium-1148 浏览器。
"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from playwright.async_api import async_playwright

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900113132"
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

PAGES = [
    ("detail", "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID),
    ("info",   "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH_ID),
]

async def test_page(browser, name, url):
    print("\n" + "=" * 60)
    print("TEST: %s => %s" % (name, url))
    print("=" * 60)

    ctx = await browser.new_context(
        viewport={"width": 414, "height": 896},
        user_agent=UA,
        locale="zh-CN", timezone_id="Asia/Shanghai",
        has_touch=True, is_mobile=True, device_scale_factor=3,
    )
    await ctx.add_init_script(STEALTH)

    page = await ctx.new_page()
    logs = []
    api_calls = []

    def on_console(m):
        text = m.text
        logs.append("[%s] %s" % (m.type, text[:300]))
        if "api001" in text or "api003" in text:
            api_calls.append(text[:200])

    page.on("console", on_console)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(10)

        body_text = await page.evaluate("document.body ? document.body.innerText : ''")
        print("Body text (%d chars):" % len(body_text))
        # 只打印前1000字符
        preview = body_text[:1000]
        print(preview)

        has_stock = any(k in body_text for k in [
            "持仓", "股票", "调仓", "买入", "卖出",
            "仓位", "成本", "盈亏",
        ])
        has_gate = "前往东方财富" in body_text or "打开APP" in body_text
        has_code = any(c.isdigit() and len([d for d in body_text[max(0,i-5):i+10] if d.isdigit()]) >= 6
                       for i, c in enumerate(body_text) if c.isdigit())

        print("\n--- 判断 ---")
        print("  有股票关键词: %s" % has_stock)
        print("  有 APP 门控: %s" % has_gate)
        print("  有数字代码: %s" % has_code)
        print("  API 调用日志: %d 条" % len(api_calls))
        for ac in api_calls[:5]:
            print("    %s" % ac)

        screenshot = r"D:\project\jiarenmens\data\debug\verify_%s.png" % name
        await page.screenshot(path=screenshot, full_page=True)
        print("  Screenshot: %s" % screenshot)

    except Exception as e:
        print("ERROR: %s" % e)
    finally:
        await page.close()
        await ctx.close()


async def main():
    print("Testing H5 pages with updated stealth script...")
    print("ZH_ID: %s" % ZH_ID)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            executable_path=CHROME,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        for name, url in PAGES:
            await test_page(browser, name, url)
        await browser.close()

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

asyncio.run(main())
