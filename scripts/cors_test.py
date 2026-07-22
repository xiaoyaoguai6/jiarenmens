"""Test API calls from page context with CORS bypass via page.route()"""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright
import aiohttp

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")

async def api_handler(route):
    request = route.request
    url = str(request.url)
    headers = dict(request.headers)
    for h in list(headers.keys()):
        if h.lower().startswith(("sec-", "origin", "referer")):
            del headers[h]
    headers["User-Agent"] = USER_AGENT
    post_data = request.post_data
    try:
        async with aiohttp.ClientSession() as session:
            if request.method == "GET":
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    body = await resp.read()
                    await route.fulfill(
                        status=resp.status,
                        headers={"Content-Type": resp.headers.get("Content-Type","application/json"), "Access-Control-Allow-Origin": "*"},
                        body=body,
                    )
            else:
                async with session.post(url, headers=headers, data=post_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    body = await resp.read()
                    await route.fulfill(
                        status=resp.status,
                        headers={"Content-Type": resp.headers.get("Content-Type","application/json"), "Access-Control-Allow-Origin": "*"},
                        body=body,
                    )
    except Exception as e:
        await route.fulfill(status=502, body=json.dumps({"error": str(e)}).encode(),
            headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"})

TEST_JS = """(async function() {
    console.log("[test] Starting API tests from page context");
    var zh = "900113132";
    async function testFetch(label, url) {
        try {
            var resp = await fetch(url);
            var text = await resp.text();
            console.log("[test] " + label + " => status=" + resp.status + " body=" + text.slice(0,300));
            return { type: label, ok: resp.ok, status: resp.status, body: text.slice(0,500) };
        } catch(e) {
            console.log("[test] " + label + " => error: " + String(e).slice(0,200));
            return { type: label, error: String(e).slice(0,200) };
        }
    }
    function buildUrl(base, params) {
        var query = Object.entries(params).map(function(e) { return e[0]+"="+encodeURIComponent(e[1]); }).join("&");
        return base + "?" + query;
    }
    var base = "https://emdcspzhapi.dfcfs.cn/rtV1";
    var results = [];
    results.push(await testFetch("rt_get_rank", buildUrl(base, { type: "rt_get_rank", rankType: "10004", recIdx: 0, recCnt: 1, rankid: 0, appVer: "9001000" })));
    results.push(await testFetch("rt_get_info", buildUrl(base, { type: "rt_get_info", zh: zh, appVer: "9001000" })));
    results.push(await testFetch("rt_get_position", buildUrl(base, { type: "rt_get_position", zh: zh, appVer: "9001000" })));
    results.push(await testFetch("rt_get_change", buildUrl(base, { type: "rt_get_change", zh: zh, appVer: "9001000" })));
    results.push(await testFetch("rt_zhuhe_yk_new", buildUrl(base, { type: "rt_zhuhe_yk_new", zh: zh, appVer: "9001000", zjzh: zh })));
    results.push(await testFetch("rt_get_info+userid", buildUrl(base, { type: "rt_get_info", zh: zh, appVer: "9001000", userid: "3043345941133016" })));
    try {
        var formBody = "type=rt_get_info&zh=" + zh + "&appVer=9001000";
        var resp = await fetch(base, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: formBody });
        var text = await resp.text();
        results.push({ type: "rt_get_info_POST", ok: resp.ok, status: resp.status, body: text.slice(0,500) });
    } catch(e) {
        results.push({ type: "rt_get_info_POST", error: String(e).slice(0,200) });
    }
    try {
        var srtUrl = "https://emdcspzhapi.dfcfs.cn/srtV1?type=rt_get_rank&rankType=10004&recIdx=0&recCnt=1&rankid=0&appVer=9001000";
        var resp = await fetch(srtUrl);
        var text = await resp.text();
        results.push({ type: "srtV1_rank", ok: resp.ok, status: resp.status, body: text.slice(0,500) });
    } catch(e) {
        results.push({ type: "srtV1_rank", error: String(e).slice(0,200) });
    }
    window.__RESULTS = JSON.stringify(results);
    console.log("[test] All done. " + results.length + " results");
})();"""

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
        
        logs = []
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:500]}"))
        page.on("pageerror", lambda e: logs.append(f"[PAGE_ERR] {str(e)[:500]}"))
        
        async def handle_js(route):
            url = route.request.url
            if any(k in url for k in ["reality_info_info", "reality/info/info", "reality_detail_detail", "reality/detail/detail"]):
                await route.fulfill(status=200, content_type="application/javascript", body=TEST_JS)
            else:
                await route.continue_()
        
        await page.route("**/*", handle_js)
        await page.route("**/emdcspzhapi.dfcfs.cn/**", api_handler)
        
        zh = "900113132"
        print(f"=== Loading info page for zh={zh} ===")
        await page.goto(
            f"https://groupwap.eastmoney.com/group/reality/info.html?zh={zh}",
            wait_until="domcontentloaded",
            timeout=30000
        )
        
        await asyncio.sleep(15)
        
        try:
            results_raw = await page.evaluate("window.__RESULTS")
            data = json.loads(results_raw)
            print("=== API Results from page (CORS bypassed) ===")
            for r in data:
                t = r.get("type", "?")
                ok = r.get("ok", "?")
                status = r.get("status", "?")
                body = r.get("body", r.get("error", ""))
                print(f"  {t:30s} | ok={ok} | status={status}")
                print(f"    -> {body[:300]}")
                print()
        except Exception as e:
            print(f"Error getting results: {e}")
            test_logs = [l for l in logs if "test" in l]
            for l in test_logs[:20]:
                print(l)
        
        await browser.close()

asyncio.run(main())
