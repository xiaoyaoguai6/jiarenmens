import asyncio, sys, codecs
from pathlib import Path
sys.path.insert(0, str(Path(r"D:\project\jiarenmens")))
from playwright.async_api import async_playwright
from src.config import USER_AGENT, MOBILE_VIEWPORT, DEVICE_SCALE_FACTOR

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False)
        ctx = await browser.new_context(
            viewport=MOBILE_VIEWPORT, user_agent=USER_AGENT,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True, device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        pool_module = __import__("src.utils.async_playwright_pool", fromlist=["AsyncPlaywrightPool"])
        await ctx.add_init_script(pool_module.AsyncPlaywrightPool._STEALTH_SCRIPT)

        page = await ctx.new_page()
        
        # Collect ALL console messages including warnings and errors
        all_console = []
        page.on("console", lambda msg: all_console.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: all_console.append(f"[pageerror] {exc}"))
        
        url = "https://groupwap.eastmoney.com/group/reality/info.html?zh=900113132"
        print(f"Opening: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait 5 seconds for initial load (before our stealth dismisses dialog)
        await asyncio.sleep(5)
        
        # Check DOM state
        body_html = await page.evaluate("document.body ? document.body.innerHTML : 'NO BODY'")
        print(f"\nBody HTML (first 2000 chars): {body_html[:2000]}")
        print(f"Body HTML length: {len(body_html)}")
        
        # Check for dialog elements
        has_dialog = await page.evaluate("""() => {
            const el = document.querySelector('[id*="confirm"], .confirm, .dialog, .mask, .alert');
            return el ? el.outerHTML.slice(0, 500) : null;
        }""")
        print(f"\nDialog element: {has_dialog}")
        
        # Check emRuntime state from page's perspective
        em_check = await page.evaluate("""() => ({
            emRuntime: window.emRuntime,
            emh5_type: typeof window.emh5,
            EMRead_type: typeof window.EMRead,
            body_children: document.body ? document.body.children.length : -1,
        })""")
        print(f"\nemRuntime check: {em_check}")
        
        # Print all console
        print(f"\n=== CONSOLE ({len(all_console)} entries) ===")
        for line in all_console:
            print(line)
        
        await page.screenshot(path=r"D:\project\jiarenmens\data\debug\qt3_screenshot.png", full_page=True)
        print("\nScreenshot saved to qt3_screenshot.png")
        
        # Now wait more to see if content loads
        await asyncio.sleep(10)
        body_html2 = await page.evaluate("document.body ? document.body.innerHTML.slice(0, 1000) : 'NO BODY'")
        print(f"\nAfter 15s - Body HTML (first 1000): {body_html2[:1000]}")
        
        await browser.close()

asyncio.run(main())
