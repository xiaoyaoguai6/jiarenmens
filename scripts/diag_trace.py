import asyncio, json, sys
sys.path.insert(0, ".")
from playwright.async_api import async_playwright
from src.config import USER_AGENT, MOBILE_VIEWPORT, DEVICE_SCALE_FACTOR
from src.utils.async_playwright_pool import _STEALTH_SCRIPT

async def diag():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport=MOBILE_VIEWPORT,
            user_agent=USER_AGENT,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True,
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        await ctx.add_init_script(_STEALTH_SCRIPT)
        page = await ctx.new_page()
        
        all_requests = []
        all_responses = []
        
        async def on_request(request):
            url = request.url
            pd = request.post_data
            all_requests.append({
                "method": request.method,
                "url": url,
                "resourceType": request.resource_type,
                "postData": pd[:500] if pd else None
            })
        async def on_response(response):
            all_responses.append({
                "status": response.status,
                "url": response.url,
                "contentType": (response.headers.get("content-type", "") or "")[:100]
            })
        
        page.on("request", on_request)
        page.on("response", on_response)
        
        urls_to_test = [
            ("detail.html", "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132"),
            ("info.html", "https://groupwap.eastmoney.com/group/reality/info.html?zh=900113132"),
        ]
        
        for label, url in urls_to_test:
            print("")
            print("=== %s ===" % label)
            print("URL: %s" % url)
            
            all_requests.clear()
            all_responses.clear()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(15)
            except Exception as e:
                print("Goto error: %s" % e)
            
            # Show all requests
            print("")
            print("All requests (%d):" % len(all_requests))
            for r in all_requests:
                url_short = r["url"].replace("https://","").replace("http://","")
                if len(url_short) > 130:
                    url_short = url_short[:130] + "..."
                extra = ""
                if r.get("postData"):
                    extra = " | POST: %s" % r["postData"][:100]
                print("  %s [%s] %s%s" % (r["method"], r["resourceType"], url_short, extra))
            
            body = await page.evaluate("document.body ? document.body.innerHTML : 'NO BODY'")
            print("")
            print("Body length: %d" % len(body))
            print("Body: %s" % body[:2000])
        
        await browser.close()

asyncio.run(diag())
