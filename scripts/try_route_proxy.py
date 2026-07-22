"""
Use Playwright route() to proxy API calls through Python, bypassing CORS.
This lets the page's JS make API calls naturally while we handle the HTTP on the server side.
"""
import asyncio
import json
import re
import requests
from pathlib import Path
from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)
STEALTH = Path(__file__).resolve().parent.parent / "src" / "utils" / "_stealth_script.js"
ZH_ID = "900113132"

# Override stealth script: replace api001/api003 with simple POST to localhost
# so Playwright route() can intercept them
STEALTH_OVERRIDES = """
// Override emDialog.emConfirm to be a no-op
if (window.emDialog) {
    window.emDialog.emConfirm = function(opts) {
        console.log("[proxy] emDialog.emConfirm intercepted");
        if (opts && opts.callback) opts.callback("cancel");
    };
}
Object.defineProperty(window, "emDialog", {
    get: function() {
        return {
            emConfirm: function(opts) {
                console.log("[proxy] emDialog.emConfirm intercepted (via getter)");
                if (opts && opts.callback) opts.callback("cancel");
            },
            loading: function() {},
            removeLoading: function() {},
            success: function() {},
            alert: function() {},
            close: function() {}
        };
    },
    configurable: true, enumerable: true
});
"""


def make_api_call(url, params):
    """Make a direct HTTP call to the East Money API."""
    headers = {
        "User-Agent": UA,
        "Referer": "https://groupwap.eastmoney.com",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        return r.text
    except Exception as e:
        return json.dumps({"error": str(e)})


async def main():
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
        # Load overrides
        await ctx.add_init_script(STEALTH_OVERRIDES)

        page = await ctx.new_page()

        # Set up route proxy for ALL requests to emdcspzhapi.dfcfs.cn
        intercepted = []

        async def proxy_handler(route):
            url = route.request.url
            method = route.request.method
            post_data = route.request.post_data
            headers = dict(route.request.headers)

            print(f"[PROXY] {method} {url[:150]}")
            intercepted.append({
                "method": method,
                "url": url,
                "post_data": post_data,
            })

            # Make the actual HTTP call from Python (bypasses CORS)
            try:
                if method == "GET":
                    r = requests.get(url, headers={
                        "User-Agent": UA,
                        "Referer": "https://groupwap.eastmoney.com",
                    }, timeout=15)
                else:
                    r = requests.post(url, data=post_data, headers={
                        "User-Agent": UA,
                        "Referer": "https://groupwap.eastmoney.com",
                        "Content-Type": "application/x-www-form-urlencoded",
                    }, timeout=15)

                print(f"  -> Response: {r.status_code} len={len(r.text)} preview={r.text[:200]}")
                await route.fulfill(
                    status=r.status_code,
                    content_type="application/json",
                    body=r.text,
                )
            except Exception as e:
                print(f"  -> Error: {e}")
                await route.abort()

        await page.route("**/emdcspzhapi.dfcfs.cn/**", proxy_handler)

        # Load the info page
        url = f"https://groupwap.eastmoney.com/group/reality/info.html?zh={ZH_ID}"
        print(f"Loading: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)

        # Check page state
        text = await page.evaluate("document.body ? document.body.innerText : ''")
        print(f"\nPage text ({len(text)} chars): {text[:500]}")

        # Try calling api001 directly from the page
        print(f"\n=== Calling api001 directly ===")
        for api_type in ["rt_get_info", "rt_get_position", "rt_get_change"]:
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
                                data: {"zh": "%s", "appVer": "9001000"},
                                success: function(t) {
                                    resolve({ok: true, data: (typeof t === 'string' ? t : JSON.stringify(t)).slice(0, 500)});
                                },
                                error: function(t) {
                                    resolve({error: String(t)});
                                }
                            });
                        });
                    })()
                """ % (api_type, ZH_ID))
                print(f"  {api_type}: {json.dumps(result, ensure_ascii=False)[:400]}")
            except Exception as e:
                print(f"  {api_type}: ERROR {e}")

        await asyncio.sleep(3)

        print(f"\n=== Intercepted {len(intercepted)} requests ===")
        for req in intercepted:
            print(f"  {req['method']} {req['url'][:200]}")
            if req['post_data']:
                print(f"    POST: {req['post_data'][:300]}")

        # Also try the change page
        print(f"\n{'='*80}")
        print("Loading change page")
        print(f"{'='*80}")
        intercepted.clear()
        url2 = f"https://groupwap.eastmoney.com/group/reality/change.html?zh={ZH_ID}"
        await page.goto(url2, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)

        # Try calling api001 for change data
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
                            type: "rt_get_change",
                            data: {"zh": "%s", "appVer": "9001000", "recIdx": 0, "recCnt": 20},
                            success: function(t) {
                                resolve({ok: true, data: (typeof t === 'string' ? t : JSON.stringify(t)).slice(0, 500)});
                            },
                            error: function(t) {
                                resolve({error: String(t)});
                            }
                        });
                    });
                })()
            """ % ZH_ID)
            print(f"  rt_get_change: {json.dumps(result, ensure_ascii=False)[:400]}")
        except Exception as e:
            print(f"  rt_get_change: ERROR {e}")

        await asyncio.sleep(3)
        print(f"  Intercepted {len(intercepted)} requests")
        for req in intercepted:
            print(f"    {req['method']} {req['url'][:200]}")

        await browser.close()


asyncio.run(main())
