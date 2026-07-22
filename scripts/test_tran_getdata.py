# -*- coding: utf-8 -*-
"""用路由代理测试 AsyncRequestTran.api001 的 /Tran/GetData 端点"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.async_api import async_playwright
import requests as req_lib

SIMPLE_STEALTH = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
function __mkBridge() {
    const stub = function() { return ''; };
    return new Proxy({}, {
        get: (t, k) => { if (k === 'toJSON' || k === Symbol.toPrimitive) return undefined; return t[k] || stub; },
        set: (t, k, v) => { t[k] = v; return true; }
    });
}
if (!window.emh5) window.emh5 = __mkBridge();
if (!window.EMProjJs) window.EMProjJs = __mkBridge();
if (!window.EMRead) window.EMRead = __mkBridge();
if (!window.emjs) window.emjs = __mkBridge();
"""

CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

session = req_lib.Session()
session.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

async def route_handler(route):
    url = route.request.url
    method = route.request.method
    post_data = route.request.post_data
    print("  [ROUTE] %s %s" % (method, url[:100]))
    if post_data:
        print("  [ROUTE] POST data: %s" % post_data[:300])
    try:
        if method == "GET":
            resp = session.get(url, timeout=15)
        else:
            resp = session.post(url, data=post_data, timeout=15)
        print("  [ROUTE] Response: %d len=%d" % (resp.status_code, len(resp.text)))
        print("  [ROUTE] Body: %s" % resp.text[:300])
        await route.fulfill(
            status=resp.status_code,
            headers={"Content-Type": "application/json"},
            body=resp.text,
        )
    except Exception as e:
        print("  [ROUTE] Error: %s" % e)
        await route.abort()

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, executable_path=CHROME,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896}, user_agent=UA,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True, device_scale_factor=3,
        )
        await ctx.add_init_script(SIMPLE_STEALTH)
        page = await ctx.new_page()

        # 拦截所有 emdcspzhapi 和 emstockdiag 请求
        await page.route("**/emdcspzhapi.dfcfs.cn/**", route_handler)
        await page.route("**/emstockdiag.eastmoney.com/**", route_handler)

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(3)

        # 测试 AsyncRequestTran.api001
        print("=== AsyncRequestTran.api001 (rt_get_rank) ===")
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.AsyncRequestTran.api001({
                url: "rtV1",
                type: "rt_get_rank",
                data: {rankType: "10004", recIdx: "0", recCnt: "3", rankid: "0", appVer: "9001000"},
                success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 10000);
        })"""), timeout=15)
        print("Result: %s" % result)

        # 测试 AsyncRequestTran.api001 with rt_get_info
        print("\n=== AsyncRequestTran.api001 (rt_get_info) ===")
        result2 = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.AsyncRequestTran.api001({
                url: "rtV1",
                type: "rt_get_info",
                data: {zh: "900113132", appVer: "9001000"},
                success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 10000);
        })"""), timeout=15)
        print("Result: %s" % result2)

        # 测试 AsyncRequestTran.api001 with rt_get_position
        print("\n=== AsyncRequestTran.api001 (rt_get_position) ===")
        result3 = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.AsyncRequestTran.api001({
                url: "rtV1",
                type: "rt_get_position",
                data: {zh: "900113132", appVer: "9001000"},
                success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 10000);
        })"""), timeout=15)
        print("Result: %s" % result3)

        await browser.close()

asyncio.run(main())
