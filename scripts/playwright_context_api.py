"""
Load the rank page in Playwright (which has working emconfig.Request.api001),
then call api001 from within the page context with various position data params.
Also intercept ALL network requests to discover hidden API calls.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)
STEALTH = Path(__file__).resolve().parent.parent / "src" / "utils" / "_stealth_script.js"
ZH = "900113132"


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
        if STEALTH.exists():
            await ctx.add_init_script(STEALTH.read_text(encoding="utf-8"))

        page = await ctx.new_page()

        # Capture ALL network requests
        all_requests = []
        def on_request(req):
            all_requests.append({"method": req.method, "url": req.url[:200]})
        page.on("request", on_request)

        # Load the rank page (this works!)
        print("Loading rank page...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/invest/reality.html",
            wait_until="networkidle",
            timeout=30000,
        )
        await asyncio.sleep(3)
        print(f"Rank page loaded. Captured {len(all_requests)} requests")

        # Check what emconfig looks like
        print("\n=== emconfig inspection ===")
        emconfig_info = await page.evaluate("""
            (function() {
                var info = {};
                if (window.emconfig) {
                    info.keys = Object.keys(window.emconfig);
                    if (window.emconfig.Request) {
                        info.requestKeys = Object.keys(window.emconfig.Request);
                        info.api001_type = typeof window.emconfig.Request.api001;
                        info.api003_type = typeof window.emconfig.Request.api003;
                    }
                    info.dsn = window.emconfig.dsn;
                    info.pkgName = window.emconfig.pkgName;
                    info.isBuildRelease = window.emconfig.isBuildRelease;
                } else {
                    info.error = "emconfig not found";
                }
                if (window.emRuntime) {
                    info.emRuntime = Object.keys(window.emRuntime);
                    info.InApp = window.emRuntime.InApp;
                }
                return info;
            })()
        """)
        print(f"  {json.dumps(emconfig_info, ensure_ascii=False)[:500]}")

        # Try calling api001 with various type names from the page context
        print("\n=== Calling api001 from page context ===")
        types_to_try = [
            "rt_get_rank",
            "rt_get_info",
            "rt_get_position",
            "rt_get_change",
            "rt_get_detail",
            "rt_get_holdings",
            "rt_get_player_info",
            "rt_get_player_position",
            "rt_get_zuhe_info",
            "rt_get_zuhe_position",
            "rt_get_group_info",
            "rt_get_stock_list",
            "rt_get_rate",
            "rt_get_trade",
            "rt_get_summary",
        ]

        for tname in types_to_try:
            try:
                result = await page.evaluate("""
                    (function(typeName) {
                        return new Promise(function(resolve) {
                            if (!window.emconfig || !window.emconfig.Request || !window.emconfig.Request.api001) {
                                resolve({error: "api001 not available"});
                                return;
                            }
                            window.emconfig.Request.api001({
                                url: "rtV1",
                                type: "get",
                                data: {type: typeName, zh: "%s", appVer: "9001000"},
                                success: function(t) {
                                    var s = (typeof t === 'string' ? t : JSON.stringify(t));
                                    resolve({ok: true, len: s.length, preview: s.slice(0, 300)});
                                },
                                error: function(t) {
                                    resolve({error: String(t).slice(0, 200)});
                                }
                            });
                        });
                    })("%s")
                """ % (tname, ZH))
                status = "HIT" if result.get("ok") else "miss"
                if result.get("ok"):
                    print(f"  *** {tname}: {result.get('preview', '')[:300]}")
                else:
                    err = result.get("error", "?")
                    print(f"  {status}: {tname} -> {err[:100]}")
            except Exception as e:
                print(f"  err: {tname} -> {e}")

        # Also try calling shipan() directly
        print("\n=== Calling shipan() from page context ===")
        for tname in ["rt_get_info", "rt_get_position", "rt_get_change"]:
            try:
                result = await page.evaluate("""
                    (function(typeName) {
                        return new Promise(function(resolve) {
                            try {
                                var m = null;
                                // Try to find the shipan module
                                var webpackJsonp = window.webpackJsonp;
                                if (webpackJsonp) {
                                    // Module 13 has shipan
                                }
                                // Try direct api001 call with different data shapes
                                window.emconfig.Request.api001({
                                    url: "rtV1",
                                    type: "get",
                                    data: {
                                        type: typeName,
                                        zh: "%s",
                                        recIdx: 0,
                                        recCnt: 20,
                                        rankType: "10004",
                                        rankid: "0",
                                        appVer: "9001000",
                                        deviceid: "DCB485C9C5E69EC1543FC90B84C6EBFA",
                                        plat: "wap"
                                    },
                                    success: function(t) {
                                        var s = (typeof t === 'string' ? t : JSON.stringify(t));
                                        resolve({ok: true, len: s.length, preview: s.slice(0, 300)});
                                    },
                                    error: function(t) {
                                        resolve({error: String(t).slice(0, 200)});
                                    }
                                });
                            } catch(e) {
                                resolve({error: e.message});
                            }
                        });
                    })("%s")
                """ % (tname, ZH))
                if result.get("ok"):
                    print(f"  *** {tname}: {result.get('preview', '')[:300]}")
                else:
                    print(f"  miss: {tname} -> {result.get('error', '?')[:100]}")
            except Exception as e:
                print(f"  err: {tname} -> {e}")

        # Try api003 with zuheV64
        print("\n=== Calling api003 (moni path) from page context ===")
        try:
            result = await page.evaluate("""
                (function() {
                    return new Promise(function(resolve) {
                        if (!window.emconfig || !window.emconfig.Request || !window.emconfig.Request.api003) {
                            resolve({error: "api003 not available"});
                            return;
                        }
                        window.emconfig.Request.api003({
                            url: "apistock/tran/getJson",
                            type: "post",
                            data: {
                                path: "zuheV64/JS.aspx",
                                pageUrl: window.location.href,
                                urlParm: "type=rt_get_position&zh=%s&appVer=9001000"
                            },
                            success: function(t) {
                                var s = (typeof t === 'string' ? t : JSON.stringify(t));
                                resolve({ok: true, len: s.length, preview: s.slice(0, 500)});
                            },
                            error: function(t) {
                                resolve({error: String(t).slice(0, 200)});
                            }
                        });
                    });
                })()
            """ % ZH)
            if result.get("ok"):
                print(f"  *** api003 HIT: {result.get('preview', '')[:500]}")
            else:
                print(f"  miss: api003 -> {result.get('error', '?')[:100]}")
        except Exception as e:
            print(f"  err: api003 -> {e}")

        # Show all captured network requests
        print(f"\n=== All captured requests ({len(all_requests)}) ===")
        for req in all_requests:
            if "dfcfs" in req["url"] or "eastmoney" in req["url"]:
                print(f"  {req['method']} {req['url']}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
