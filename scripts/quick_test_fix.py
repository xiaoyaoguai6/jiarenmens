import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(r"D:\project\jiarenmens")))
from playwright.async_api import async_playwright
from src.config import USER_AGENT, MOBILE_VIEWPORT, DEVICE_SCALE_FACTOR

# Force re-read the stealth script (Python module caching issue)
import importlib
import src.utils.async_playwright_pool as pool_mod
importlib.reload(pool_mod)
_STEALTH_SCRIPT = pool_mod._STEALTH_SCRIPT
print(f"Stealth script length: {len(_STEALTH_SCRIPT)}")

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
        ])
        ctx = await browser.new_context(
            viewport=MOBILE_VIEWPORT,
            user_agent=USER_AGENT,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True,
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        await ctx.add_init_script(_STEALTH_SCRIPT)
        page = await ctx.new_page()

        logs = []
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:200]}"))
        page.on("pageerror", lambda e: logs.append(f"[ERR] {str(e)[:200]}"))

        url = "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132"
        print(f"Fetching: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(8)

        body = await page.evaluate("document.body ? document.body.innerHTML : 'NO BODY'")
        print(f"Body length: {len(body)}")
        print(f"Body preview (500 chars): {body[:500]}")

        # Check for key data elements
        has_positions = await page.evaluate("!!document.querySelector('[class*=position]')")
        has_trades = await page.evaluate("!!document.querySelector('[class*=change]')")
        print(f"Has position elements: {has_positions}")
        print(f"Has trade elements: {has_trades}")

        print(f"\n=== Console ({len(logs)} entries) ===")
        for l in logs: print(l)

asyncio.run(test())
