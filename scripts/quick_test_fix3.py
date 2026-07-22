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
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:400]}"))
        page.on("pageerror", lambda e: logs.append(f"[ERR] {str(e)[:400]}"))

        # Log API calls
        api_calls = []
        async def on_request(request):
            url = request.url
            if "emdcspzhapi" in url or "apistock" in url:
                method = request.method
                post_data = request.post_data
                api_calls.append(f"[API] {method} {url[:150]} | data: {str(post_data)[:200] if post_data else 'N/A'}")
        page.on("request", on_request)

        url = "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132"
        print(f"Fetching: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(15)  # wait longer

        body = await page.evaluate("document.body ? document.body.innerHTML : 'NO BODY'")
        print(f"Body length: {len(body)}")

        # Check for dynamic content
        has_positions = await page.evaluate("!!document.querySelector('#container tr')")
        has_loading = await page.evaluate("!!document.querySelector('.loading')")
        console_only = await page.evaluate("document.querySelectorAll('.no-data, .empty').length > 0")
        print(f"Has position rows: {has_positions}")
        print(f"Has loading visible: {has_loading}")
        print(f"Has no-data/empty: {console_only}")

        print(f"\n=== API calls ({len(api_calls)}) ===")
        for a in api_calls: print(a)

        print(f"\n=== Console ({len(logs)} entries) ===")
        for l in logs: print(l)

        # Check emRuntime and other bridge object state
        bridge_check = await page.evaluate("() => ({ emRuntime: !!window.emRuntime, emh5: typeof window.emh5, EMRead: typeof window.EMRead, emconfig: typeof window.emconfig })")
        print(f"\nBridge check: {bridge_check}")

asyncio.run(test())
