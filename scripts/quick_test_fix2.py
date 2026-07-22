import asyncio, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(r"D:\project\jiarenmens")))
from playwright.async_api import async_playwright
from src.config import USER_AGENT, MOBILE_VIEWPORT, DEVICE_SCALE_FACTOR

import importlib
import src.utils.async_playwright_pool as pool_mod
importlib.reload(pool_mod)
_STEALTH_SCRIPT = pool_mod._STEALTH_SCRIPT

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
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:300]}"))
        page.on("pageerror", lambda e: logs.append(f"[ERR] {str(e)[:300]}"))
        
        # Log all network requests
        requests = []
        page.on("request", lambda r: requests.append(f"[REQ] {r.method} {r.url[:200]}"))
        page.on("response", lambda r: requests.append(f"[RESP] {r.status} {r.url[:200]}"))

        url = "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132"
        print(f"Fetching: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(12)

        body = await page.evaluate("document.body ? document.body.innerHTML : 'NO BODY'")
        print(f"Body length: {len(body)}")
        print(f"Body (first 2000): {body[:2000]}")

        print(f"\n=== Network ({len(requests)} requests) ===")
        for r in requests[-30:]: print(r)

        print(f"\n=== Console ({len(logs)} entries) ===")
        for l in logs: print(l)

asyncio.run(test())
