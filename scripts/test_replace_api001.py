# -*- coding: utf-8 -*-
"""
方案：在页面 JS 加载完成后，强制替换 api001 为我们的 fetch 版本。
用 Playwright route() 绕过 CORS。
"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright
import requests as req_lib

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900113132"
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

session = req_lib.Session()
session.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

async def route_handler(route):
    request = route.request
    url = request.url
    method = request.method
    try:
        if method == "GET":
            resp = session.get(url, timeout=15)
        else:
            resp = session.post(url, data=request.post_data, timeout=15)
        await route.fulfill(
            status=resp.status_code,
            headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            body=resp.text,
        )
    except Exception as e:
        await route.abort()

# 注入脚本：在 common.js 加载后，强制替换 api001 为 fetch 版本
REPLACE_API001 = """
(function() {
    // 等待 emconfig 初始化
    var tries = 0;
    function waitAndReplace() {
        tries++;
        if (window.emconfig && window.emconfig.Request) {
            console.log("[replace] emconfig found, replacing api001...");
            window.emconfig.Request.api001 = function(opts) {
                var data = opts.data || {};
                var parts = [];
                for (var k in data) {
                    if (data.hasOwnProperty(k))
                        parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(data[k]));
                }
                var url = "https://emdcspzhapi.dfcfs.cn/" + (opts.url || "rtV1");
                if (parts.length) url += "?" + parts.join("&");
                console.log("[replace] api001 fetch:", url.slice(0, 150));
                fetch(url)
                    .then(function(r) { return r.text(); })
                    .then(function(t) {
                        console.log("[replace] api001 success, len:", t.length);
                        if (opts.success) opts.success(t);
                    })
                    .catch(function(e) {
                        console.log("[replace] api001 error:", e);
                        if (opts.error) opts.error(String(e));
                    });
            };
            console.log("[replace] api001 replaced successfully");
        } else if (tries < 50) {
            setTimeout(waitAndReplace, 200);
        } else {
            console.log("[replace] emconfig not found after 50 tries");
        }
    }
    waitAndReplace();
})();
"""

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
        # 先注入 stealth，再注入替换脚本
        await ctx.add_init_script(STEALTH)
        await ctx.add_init_script(REPLACE_API001)

        page = await ctx.new_page()

        # 拦截 emdcspzhapi 请求
        await page.route("**/*emdcspzhapi*", route_handler)

        console_msgs = []
        proxied_urls = []
        page.on("console", lambda m: console_msgs.append("[%s] %s" % (m.type, m.text[:300])))

        print("Loading page...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(5)

        # 检查替换是否成功
        check = await page.evaluate("""() => ({
            hasApi001: !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api001),
            api001Str: window.emconfig && window.emconfig.Request && window.emconfig.Request.api001
                ? window.emconfig.Request.api001.toString().slice(0, 200) : 'N/A',
        })""")
        print("api001 replaced: %s" % ("fetch" in check.get("api001Str", "")))
        print("api001 source: %s" % check.get("api001Str", "")[:150])

        # 调用 api001
        print("\n=== Calling api001 ===")
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.Request.api001({
                url: "rtV1",
                type: "rt_get_info",
                data: {zh: "900113132", appVer: "9001000"},
                success: function(t) { resolve({ok: true, len: t.length, preview: t.slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 10000);
        })"""), timeout=15)
        print("  Result: %s" % result)

        # 打印相关日志
        print("\n=== Console logs ===")
        for m in console_msgs:
            if "replace" in m or "api001" in m or "error" in m.lower():
                print("  %s" % m)

        # 检查页面内容
        body = await page.evaluate("document.body ? document.body.innerText : ''")
        print("\n=== Page text ===")
        print(body[:500])

        await browser.close()

asyncio.run(main())
