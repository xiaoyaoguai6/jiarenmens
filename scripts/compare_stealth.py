# -*- coding: utf-8 -*-
"""对比测试：有无 stealth 脚本的页面加载效果"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900113132"
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
URL = "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID

async def run_test(browser, label, use_stealth):
    print("\n" + "=" * 60)
    print("TEST: %s (stealth=%s)" % (label, use_stealth))
    print("=" * 60)

    ctx = await browser.new_context(
        viewport={"width": 414, "height": 896},
        user_agent=UA,
        locale="zh-CN", timezone_id="Asia/Shanghai",
        has_touch=True, is_mobile=True, device_scale_factor=3,
    )
    if use_stealth:
        await ctx.add_init_script(STEALTH)

    page = await ctx.new_page()
    errors = []
    console_msgs = []
    network_reqs = []

    page.on("pageerror", lambda e: errors.append(str(e)[:300]))
    page.on("console", lambda m: console_msgs.append("[%s] %s" % (m.type, m.text[:200])))
    page.on("request", lambda r: network_reqs.append("%s %s" % (r.method, r.url[:120])))

    try:
        resp = await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        print("  HTTP status: %s" % (resp.status if resp else "None"))
        await asyncio.sleep(8)

        html = await page.content()
        body = await page.evaluate("document.body ? document.body.innerHTML : 'NO BODY'")
        title = await page.title()

        print("  Title: %s" % title)
        print("  HTML length: %d" % len(html))
        print("  Body length: %d" % len(body))
        print("  Body preview: %s" % body[:500])

        print("\n  Page errors (%d):" % len(errors))
        for e in errors[:10]:
            print("    %s" % e)

        print("\n  Console msgs (%d):" % len(console_msgs))
        for m in console_msgs[:15]:
            print("    %s" % m)

        print("\n  Network requests (%d):" % len(network_reqs))
        # 只显示非静态资源请求
        api_reqs = [r for r in network_reqs if not any(ext in r for ext in [".js", ".css", ".png", ".jpg", ".gif", ".woff", ".ttf", ".svg", ".ico"])]
        for r in api_reqs[:15]:
            print("    %s" % r)

        await page.screenshot(path=r"D:\project\jiarenmens\data\debug\verify_%s.png" % label, full_page=True)

    except Exception as e:
        print("  ERROR: %s" % e)
    finally:
        await page.close()
        await ctx.close()

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            executable_path=CHROME,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        await run_test(browser, "no_stealth", use_stealth=False)
        await run_test(browser, "with_stealth", use_stealth=True)
        await browser.close()

asyncio.run(main())
