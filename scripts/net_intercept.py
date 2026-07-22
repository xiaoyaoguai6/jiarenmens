"""
Use Playwright to load the detail page and intercept all network requests
to discover the actual API endpoints and parameters used by the page.
"""
import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

STEALTH = Path(__file__).resolve().parent.parent / "src" / "utils" / "_stealth_script.js"

ZH_ID = "900113132"


async def main():
    all_requests = []
    all_responses = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent=UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            has_touch=True,
            is_mobile=True,
            device_scale_factor=3,
        )

        # Load stealth script
        if STEALTH.exists():
            await ctx.add_init_script(STEALTH.read_text(encoding="utf-8"))

        page = await ctx.new_page()

        # Intercept ALL network requests
        def on_request(request):
            url = request.url
            if any(skip in url for skip in [".css", ".png", ".jpg", ".gif", ".ico", ".woff", ".ttf", ".svg"]):
                return
            info = {
                "method": request.method,
                "url": url[:200],
                "post_data": request.post_data[:500] if request.post_data else None,
                "headers": dict(list(request.headers.items())[:10]),
            }
            all_requests.append(info)
            if "eastmoney" in url or "dfcfs" in url:
                print(f"[REQ] {request.method} {url[:150]}")
                if request.post_data:
                    print(f"      POST: {request.post_data[:300]}")

        def on_response(response):
            url = response.url
            if "eastmoney" in url or "dfcfs" in url:
                print(f"[RES] {response.status} {url[:150]}")
                all_responses.append({
                    "url": url[:200],
                    "status": response.status,
                })

        page.on("request", on_request)
        page.on("response", on_response)

        # Load the info page (which has position/trade data templates)
        urls_to_try = [
            f"https://groupwap.eastmoney.com/group/reality/info.html?zh={ZH_ID}",
            f"https://groupwap.eastmoney.com/group/reality/detail.html?zh={ZH_ID}",
            f"https://groupwap.eastmoney.com/group/reality/change.html?zh={ZH_ID}",
        ]

        for url in urls_to_try:
            print(f"\n{'='*80}")
            print(f"Loading: {url}")
            print(f"{'='*80}")
            all_requests.clear()
            all_responses.clear()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(5)

                # Try to dismiss the app dialog by clicking "cancel"
                try:
                    cancel_btn = page.locator("text=取消").first
                    if await cancel_btn.is_visible(timeout=2000):
                        await cancel_btn.click()
                        print("  -> Clicked cancel button")
                        await asyncio.sleep(3)
                except Exception:
                    pass

                # Check what the page rendered
                content = await page.content()
                text = await page.evaluate("document.body.innerText")
                print(f"  Page text ({len(text)} chars): {text[:200]}")

                # Log all eastmoney API requests
                print(f"\n  Total eastmoney requests: {len([r for r in all_requests if 'eastmoney' in r['url'] or 'dfcfs' in r['url']])}")

            except Exception as e:
                print(f"  ERROR: {e}")

        # Now try to call the API from within the browser context
        print(f"\n{'='*80}")
        print("Testing API from within browser context (with emconfig)")
        print(f"{'='*80}")

        await page.goto(f"https://groupwap.eastmoney.com/group/reality/info.html?zh={ZH_ID}",
                         wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)

        # Check if emconfig is available
        emconfig_check = await page.evaluate("""
            (function() {
                var result = {};
                result.hasEmconfig = !!window.emconfig;
                result.hasRequest = !!(window.emconfig && window.emconfig.Request);
                result.hasApi001 = !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api001);
                result.hasApi003 = !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api003);
                result.hasEmh5 = !!window.emh5;
                result.hasEMProjJs = !!window.EMProjJs;
                result.hasEMRead = !!window.EMRead;
                return result;
            })()
        """)
        print(f"emconfig check: {json.dumps(emconfig_check)}")

        # Try calling APIs from browser context
        api_tests = [
            ("rt_get_info", {"zh": ZH_ID, "appVer": "9001000"}),
            ("rt_get_position", {"zh": ZH_ID, "appVer": "9001000"}),
            ("rt_get_change", {"zh": ZH_ID, "appVer": "9001000"}),
            ("rt_get_rank", {"rankType": "10004", "recIdx": 0, "recCnt": 1, "rankid": 0, "appVer": "9001000"}),
        ]

        for api_type, data in api_tests:
            try:
                result = await page.evaluate("""
                    (function() {
                        return new Promise(function(resolve) {
                            if (!window.emconfig || !window.emconfig.Request || !window.emconfig.Request.api001) {
                                resolve({error: "api001 not available"});
                                return;
                            }
                            window.emconfig.Request.api001({
                                url: "rtV1",
                                type: "%s",
                                data: %s,
                                success: function(t) {
                                    resolve({ok: true, data: (typeof t === 'string' ? t : JSON.stringify(t)).slice(0, 500)});
                                },
                                error: function(t) {
                                    resolve({error: String(t)});
                                }
                            });
                        });
                    })()
                """ % (api_type, json.dumps(data)))
                print(f"  api001 type={api_type}: {json.dumps(result, ensure_ascii=False)[:400]}")
            except Exception as e:
                print(f"  api001 type={api_type}: ERROR {e}")

        await browser.close()


asyncio.run(main())
