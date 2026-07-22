# -*- coding: utf-8 -*-
"""
最终方案：修改 emconfig 的 api001 指向 emstockdiag/apistock/Tran/GetData，
然后触发页面自己的数据加载代码。
"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright
import requests as req_lib

CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

session = req_lib.Session()
session.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

# 简单 stealth（不覆盖 api001）
STEALTH = """
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

# 在页面 JS 加载后，修改 emconfig 的域名配置
RECONFIG = """
(function() {
    var tries = 0;
    function reconfig() {
        tries++;
        var ec = window.emconfig;
        if (!ec || !ec.Request) {
            if (tries < 50) setTimeout(reconfig, 200);
            return;
        }
        // 修改 api001 的目标为 emstockdiag
        var origApi001 = ec.Request.api001;
        ec.Request.api001 = function(opts) {
            // 构造 emstockdiag 格式的请求
            var body = {
                path: "rspThird/community/" + (opts.type || "get") + "_handler",
                parm: JSON.stringify(opts.data || {}),
                header: {
                    appkey: "a8157f5ef970edda2c103e192b6dc3e5",
                    Referer: "http://www.eastmoney.com"
                },
                track: "sys_" + Date.now(),
                pageUrl: location.href
            };
            fetch("https://emstockdiag.eastmoney.com/apistock/Tran/GetData", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(body)
            })
            .then(function(r) { return r.text(); })
            .then(function(t) {
                try {
                    var d = JSON.parse(t);
                    if (d.RCode === 200 && d.RData) {
                        var inner = JSON.parse(d.RData);
                        if (inner.state === 0 && inner.data) {
                            if (opts.success) opts.success(JSON.stringify(inner.data));
                        } else {
                            if (opts.error) opts.error(inner.message || "no data");
                        }
                    } else {
                        if (opts.error) opts.error("RCode=" + d.RCode);
                    }
                } catch(e) {
                    if (opts.error) opts.error(e.message);
                }
            })
            .catch(function(e) {
                if (opts.error) opts.error(String(e));
            });
        };
        console.log("[reconfig] api001 redirected to emstockdiag");
    }
    reconfig();
})();
"""

async def main():
    ZH_ID = "900113132"

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
        await ctx.add_init_script(STEALTH)
        await ctx.add_init_script(RECONFIG)
        page = await ctx.new_page()

        console = []
        page.on("console", lambda m: console.append("[%s] %s" % (m.type, m.text[:200])))

        # 拦截 emstockdiag 请求
        async def route_handler(route):
            url = route.request.url
            try:
                if route.request.method == "GET":
                    resp = session.get(url, timeout=15)
                else:
                    resp = session.post(url, data=route.request.post_data, timeout=15)
                await route.fulfill(
                    status=resp.status_code,
                    headers={"Content-Type": "application/json"},
                    body=resp.text,
                )
            except Exception as e:
                await route.abort()

        await page.route("**/emstockdiag.eastmoney.com/**", route_handler)
        await page.route("**/emdcspzhapi.dfcfs.cn/**", route_handler)

        print("Loading page...")
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(8)

        # 检查页面内容
        body = await page.evaluate("document.body ? document.body.innerText : ''")
        print("Page text (%d chars):" % len(body))
        print(body[:500])

        # 检查 emconfig 是否已重新配置
        check = await page.evaluate("""() => ({
            hasApi001: !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api001),
            api001Str: window.emconfig && window.emconfig.Request && window.emconfig.Request.api001
                ? window.emconfig.Request.api001.toString().slice(0, 100) : 'N/A',
        })""")
        print("\napi001: %s" % check.get("api001Str", "")[:100])
        print("Is redirected: %s" % ("emstockdiag" in check.get("api001Str", "")))

        # 打印控制台日志
        print("\nConsole:")
        for m in console:
            if "reconfig" in m or "api001" in m or "error" in m.lower():
                print("  %s" % m)

        await browser.close()

asyncio.run(main())
