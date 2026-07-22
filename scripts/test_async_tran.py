# -*- coding: utf-8 -*-
"""测试 AsyncRequestTran.api001 和域名配置"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.async_api import async_playwright

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
        page.on("request", lambda r: all_reqs.append({"url": r.url, "method": r.method}))

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(5)

        # 检查域名配置
        print("=== 域名 API 配置 ===")
        domain_config = await page.evaluate("""() => {
            var ec = window.emconfig;
            if (!ec) return {};
            var results = {};
            var domains = ['default', 'my.eastmoney.com', '172.30.66.31', 'groupwap.eastmoney.com', 'empts.eastmoney.com'];
            for (var d of domains) {
                if (ec[d] && ec[d].api) {
                    results[d] = {};
                    for (var k in ec[d].api) {
                        results[d][k] = String(ec[d].api[k]).slice(0, 200);
                    }
                }
            }
            return results;
        }""")
        for domain, apis in domain_config.items():
            print("  %s:" % domain)
            for k, v in apis.items():
                print("    %s = %s" % (k, v))

        # 测试 AsyncRequestTran.api001
        print("\n=== AsyncRequestTran.api001 ===")
        all_reqs.clear()
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            var ec = window.emconfig;
            if (!ec.AsyncRequestTran || !ec.AsyncRequestTran.api001) {
                resolve({error: 'no AsyncRequestTran.api001'}); return;
            }
            ec.AsyncRequestTran.api001({
                url: "rtV1",
                type: "rt_get_rank",
                data: {rankType: "10004", recIdx: "0", recCnt: "3", rankid: "0", appVer: "9001000"},
                success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("Result: %s" % result)
        print("Requests: %d" % len(all_reqs))
        for r in all_reqs[:5]:
            print("  %s %s" % (r["method"], r["url"][:150]))

        # 测试 AsyncRequestTran.api003
        print("\n=== AsyncRequestTran.api003 ===")
        all_reqs.clear()
        result2 = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            var ec = window.emconfig;
            if (!ec.AsyncRequestTran || !ec.AsyncRequestTran.api003) {
                resolve({error: 'no AsyncRequestTran.api003'}); return;
            }
            ec.AsyncRequestTran.api003({
                data: {
                    path: "zuheV64/JS.aspx",
                    pageUrl: location.href,
                    urlParm: JSON.stringify({type: "rt_get_rank", rankType: "10004", recIdx: "0", recCnt: "3", rankid: "0", appVer: "9001000"}),
                },
                success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("Result: %s" % result2)
        print("Requests: %d" % len(all_reqs))
        for r in all_reqs[:5]:
            print("  %s %s" % (r["method"], r["url"][:150]))

        await browser.close()

asyncio.run(main())
