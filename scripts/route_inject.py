"""Use page.route() to block patched page JS and inject custom data-loading logic."""
import asyncio, json, re
from pathlib import Path
from playwright.async_api import async_playwright

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

# Read full stealth script
stealth = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")

# Custom page JS that uses common.js wrappers to load data
CUSTOM_INFO_JS = """
(function() {
    console.log("[inject] Custom info loader running");
    
    // Wait for common.js to init emconfig
    var checks = 0;
    function waitForEmconfig(cb) {
        if (window.emconfig && window.emconfig.Request && window.emconfig.Request.api001) {
            cb();
        } else if (checks < 50) {
            checks++;
            setTimeout(function() { waitForEmconfig(cb); }, 200);
        } else {
            console.log("[inject] emconfig never loaded");
        }
    }
    
    waitForEmconfig(function() {
        console.log("[inject] emconfig ready, loading player data...");
        var zh = location.search.match(/zh=([\d]+)/);
        zh = zh ? zh[1] : "";
        
        if (!zh) {
            document.getElementById("detail-content").innerHTML = "<p>No zh parameter</p>";
            return;
        }
        
        // Call the player detail API
        window.emconfig.Request.api001({
            url: "rtV1",
            type: "rt_get_info",
            data: {
                zh: zh,
                zjzh: zh,
                appVer: "9001000",
            },
            success: function(data) {
                console.log("[inject] rt_get_info success:", data.slice(0, 300));
                try {
                    var result = typeof data === "string" ? JSON.parse(data) : data;
                    document.getElementById("detail-content").innerHTML = 
                        "<pre style='padding:10px;font-size:12px;white-space:pre-wrap'>" +
                        JSON.stringify(result, null, 2) +
                        "</pre>";
                } catch(e) {
                    document.getElementById("detail-content").innerHTML = 
                        "<pre style='padding:10px'>" + data.slice(0, 2000) + "</pre>";
                }
            },
            error: function(err) {
                console.log("[inject] rt_get_info error:", err);
                document.getElementById("detail-content").innerHTML = 
                    "<p style='padding:10px;color:red'>API Error: " + String(err).slice(0, 500) + "</p>";
            }
        });
    });
})();
"""

CUSTOM_DETAIL_JS = """
(function() {
    console.log("[inject] Custom detail loader running");
    
    var checks = 0;
    function waitForEmconfig(cb) {
        if (window.emconfig && window.emconfig.Request && window.emconfig.Request.api001) {
            cb();
        } else if (checks < 50) {
            checks++;
            setTimeout(function() { waitForEmconfig(cb); }, 200);
        } else {
            console.log("[inject] emconfig never loaded");
        }
    }
    
    waitForEmconfig(function() {
        console.log("[inject] emconfig ready, loading position data...");
        var zh = location.search.match(/zh=([\d]+)/);
        zh = zh ? zh[1] : "";
        
        if (!zh) return;
        
        // Try multiple API types
        var types = ["rt_get_position", "rt_get_info", "rt_get_zjzh_detail", "rt_zhuhe_yk_new"];
        var results = {};
        var done = 0;
        
        types.forEach(function(t) {
            window.emconfig.Request.api001({
                url: "rtV1",
                type: t,
                data: { zh: zh, zjzh: zh, appVer: "9001000", uid: "" },
                success: function(data) {
                    results[t] = { ok: true, data: data.slice(0, 500) };
                    done++;
                    if (done === types.length) render();
                },
                error: function(err) {
                    results[t] = { ok: false, err: String(err).slice(0, 300) };
                    done++;
                    if (done === types.length) render();
                }
            });
        });
        
        function render() {
            document.getElementById("container").innerHTML = 
                "<pre style='padding:10px;font-size:12px;white-space:pre-wrap'>" +
                JSON.stringify(results, null, 2) +
                "</pre>";
        }
    });
})();
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent=USER_AGENT,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True,
            device_scale_factor=3,
        )
        await ctx.add_init_script(stealth)
        page = await ctx.new_page()
        
        logs = []
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:400]}"))
        page.on("pageerror", lambda e: logs.append(f"[PAGE_ERR] {str(e)[:400]}"))
        
        # Intercept page-specific JS and replace with custom loader
        async def handle_route(route):
            url = route.request.url
            if "reality/info/info" in url or "reality_info_info" in url:
                print(f"[route] Intercepted info page JS, injecting custom loader")
                await route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=CUSTOM_INFO_JS,
                )
            elif "reality/detail/detail" in url or "reality_detail_detail" in url:
                print(f"[route] Intercepted detail page JS, injecting custom loader")
                await route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=CUSTOM_DETAIL_JS,
                )
            else:
                await route.continue_()
        
        await page.route("**/*", handle_route)
        
        # Load info page
        zh = "900113132"
        print(f"\n=== Loading info page for zh={zh} ===")
        await page.goto(
            f"https://groupwap.eastmoney.com/group/reality/info.html?zh={zh}",
            wait_until="domcontentloaded",
            timeout=30000
        )
        await asyncio.sleep(10)
        
        body = await page.evaluate("document.body ? document.body.innerHTML : 'NO BODY'")
        print(f"Body length: {len(body)}")
        print(f"Body preview: {body[:800]}")
        
        # Filter relevant logs
        relevant = [l for l in logs if any(k in l for k in ["inject", "stealth", "api001", "api003", "PAGE_ERR", "emconfig"])]
        print(f"\n--- Relevant logs ({len(relevant)}/{len(logs)}) ---")
        for l in relevant[:30]:
            print(l)
        
        await browser.close()

asyncio.run(main())
