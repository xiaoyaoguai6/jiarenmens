"""Test API calls from within a Playwright page context (bypasses CORS/network restrictions)."""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

STEALTH = """
Object.defineProperty(navigator, "webdriver", { get: () => undefined });
window.emRuntime = { InApp: true, InIOSApp: true, OS: "iOS", AppVersion: "13.5.0", DeviceId: "DCB" };

async function test_apis() {
    const zh = "900113132";
    const url = "https://emdcspzhapi.dfcfs.cn/rtV1";
    const types = [
        "rt_get_info",
        "rt_get_zjzh_detail",
        "rt_get_user_detail",
        "rt_detail",
        "rt_info",
        "rt_zhuhe_yk_new",
    ];

    const results = [];
    for (const t of types) {
        const params = new URLSearchParams({
            type: t,
            zh: zh,
            zjzh: zh,
            appVer: "9001000",
            userid: "3043345941133016",
        });
        try {
            const resp = await fetch(url + "?" + params.toString());
            const text = await resp.text();
            results.push({ type: t, ok: resp.ok, text: text.slice(0, 500) });
        } catch (e) {
            results.push({ type: t, error: String(e).slice(0, 200) });
        }
    }
    
    // Also try api003 via POST
    try {
        const body = new URLSearchParams({
            path: "zuheV64/JS.aspx",
            pageUrl: "https://groupwap.eastmoney.com/group/reality/info.html",
            urlParm: JSON.stringify({ zh: zh }),
        });
        const resp = await fetch("https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: body.toString(),
        });
        const text = await resp.text();
        results.push({ type: "api003_post", ok: resp.ok, text: text.slice(0, 500) });
    } catch (e) {
        results.push({ type: "api003_post", error: String(e).slice(0, 200) });
    }
    
    // Try emstockdiag
    try {
        const body2 = new URLSearchParams({
            path: "zuheV64/JS.aspx",
            pageUrl: "https://groupwap.eastmoney.com/group/reality/info.html",
            urlParm: JSON.stringify({ zh: zh }),
        });
        const resp = await fetch("https://emstockdiag.eastmoney.com/apistock/tran/getJson", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: body2.toString(),
        });
        const text = await resp.text();
        results.push({ type: "api003_emstockdiag", ok: resp.ok, text: text.slice(0, 500) });
    } catch (e) {
        results.push({ type: "api003_emstockdiag", error: String(e).slice(0, 200) });
    }
    
    return JSON.stringify(results);
}

// Expose tester
window.__test_apis = test_apis;
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
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()
        
        # Navigate to the real page first to set proper origin/referer
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/info.html?zh=900113132",
            wait_until="domcontentloaded",
            timeout=30000
        )
        await asyncio.sleep(3)
        
        # Call our test function
        result = await page.evaluate("window.__test_apis()")
        data = json.loads(result)
        print("=== API results from page context ===")
        for r in data:
            t = r.get("type", "")
            ok = r.get("ok", "?")
            txt = r.get("text", "") or r.get("error", "")
            print(f"  {t}: ok={ok} | {txt[:120]}")
        
        await browser.close()

asyncio.run(main())
