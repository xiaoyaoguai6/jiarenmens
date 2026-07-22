# -*- coding: utf-8 -*-
"""分析页面 api001 的闭包变量，找出真实的 API base URL"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

SIMPLE_STEALTH = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
function __mkBridge() {
    const stub = function() { return ''; };
    return new Proxy({}, {
        get: (t, k) => {
            if (k === 'toJSON' || k === Symbol.toPrimitive) return undefined;
            return t[k] || stub;
        },
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

        all_reqs = []
        page.on("request", lambda r: all_reqs.append(r.url))

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(5)

        # 尝试提取 api001 的闭包变量 'i' (base URL)
        result = await page.evaluate("""() => {
            try {
                var fn = window.emconfig.Request.api001;
                var fnStr = fn.toString();
                // 通过调用 api001 并拦截 URL 来获取 base URL
                return new Promise((resolve) => {
                    var origFetch = window.fetch;
                    window.fetch = function(url, opts) {
                        resolve({url: url, method: opts?.method || 'GET'});
                        window.fetch = origFetch;
                        return origFetch.apply(this, arguments);
                    };
                    var origXHR = XMLHttpRequest.prototype.open;
                    XMLHttpRequest.prototype.open = function(method, url) {
                        resolve({url: url, method: method, type: 'xhr'});
                        XMLHttpRequest.prototype.open = origXHR;
                        return origXHR.apply(this, arguments);
                    };
                    // 调用 api001
                    window.emconfig.Request.api001({
                        url: "rtV1",
                        type: "rt_get_rank",
                        data: {rankType: "10004", recIdx: "0", recCnt: "1", rankid: "0", appVer: "9001000"},
                        success: function() {},
                        error: function() {}
                    });
                    setTimeout(() => resolve({timeout: true, noRequest: true}), 5000);
                });
            } catch(e) { return {error: e.message}; }
        }""")
        print("api001 request details: %s" % result)

        # 也检查 emconfig 的完整结构
        ec_check = await page.evaluate("""() => {
            var ec = window.emconfig;
            return {
                keys: ec ? Object.keys(ec) : [],
                requestKeys: ec && ec.Request ? Object.keys(ec.Request) : [],
                baseUrl: ec && ec.baseUrl ? ec.baseUrl : 'N/A',
                apiHost: ec && ec.apiHost ? ec.apiHost : 'N/A',
            };
        }""")
        print("\nemconfig structure: %s" % ec_check)

        # 检查所有全局变量中包含 URL 的
        url_globals = await page.evaluate("""() => {
            var results = [];
            var check = ['apiHost', 'baseUrl', 'apiUrl', 'serverUrl', 'rtV1url', 'push2url'];
            for (var k of check) {
                if (window[k]) results.push(k + '=' + window[k]);
            }
            return results;
        }""")
        print("\nURL globals: %s" % url_globals)

        await browser.close()

asyncio.run(main())
