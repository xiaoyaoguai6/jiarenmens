# -*- coding: utf-8 -*-
"""测试 emconfig 的各种 Request 方法"""
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
        all_resps = []
        page.on("request", lambda r: all_reqs.append({"url": r.url, "method": r.method}))
        page.on("response", lambda r: all_resps.append({"url": r.url, "status": r.status}))

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(5)

        # 列出 emconfig 的所有方法
        methods = await page.evaluate("""() => {
            var ec = window.emconfig;
            if (!ec) return [];
            var results = [];
            for (var k in ec) {
                var v = ec[k];
                if (typeof v === 'function') {
                    results.push({name: k, type: 'function', str: v.toString().slice(0, 100)});
                } else if (typeof v === 'object' && v !== null) {
                    var subKeys = [];
                    for (var sk in v) {
                        subKeys.push(sk + ':' + typeof v[sk]);
                    }
                    results.push({name: k, type: 'object', keys: subKeys.join(', ')});
                } else {
                    results.push({name: k, type: typeof v, value: String(v).slice(0, 50)});
                }
            }
            return results;
        }""")
        print("=== emconfig methods ===")
        for m in methods:
            if m['type'] == 'function':
                print("  %s(): %s" % (m['name'], m['str']))
            elif m['type'] == 'object':
                print("  %s.{%s}" % (m['name'], m['keys']))
            else:
                print("  %s = %s (%s)" % (m['name'], m['value'], m['type']))

        # 测试 AsyncRequestTran
        print("\n=== Testing AsyncRequestTran ===")
        all_reqs.clear()
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            var ec = window.emconfig;
            if (!ec.AsyncRequestTran) { resolve({error: 'no AsyncRequestTran'}); return; }
            try {
                ec.AsyncRequestTran({
                    url: "rtV1",
                    type: "rt_get_rank",
                    data: {rankType: "10004", recIdx: "0", recCnt: "3", rankid: "0", appVer: "9001000"},
                    success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                    error: function(e) { resolve({error: String(e)}); }
                });
            } catch(e) { resolve({exception: e.message}); }
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("Result: %s" % result)
        print("Requests: %d" % len(all_reqs))
        for r in all_reqs[:5]:
            print("  %s %s" % (r["method"], r["url"][:150]))

        # 测试 AsyncRequestTranJson
        print("\n=== Testing AsyncRequestTranJson ===")
        all_reqs.clear()
        result2 = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            var ec = window.emconfig;
            if (!ec.AsyncRequestTranJson) { resolve({error: 'no AsyncRequestTranJson'}); return; }
            try {
                ec.AsyncRequestTranJson({
                    url: "rtV1",
                    type: "rt_get_rank",
                    data: {rankType: "10004", recIdx: "0", recCnt: "3", rankid: "0", appVer: "9001000"},
                    success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                    error: function(e) { resolve({error: String(e)}); }
                });
            } catch(e) { resolve({exception: e.message}); }
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("Result: %s" % result2)
        print("Requests: %d" % len(all_reqs))

        # 测试 RequestJsonp
        print("\n=== Testing RequestJsonp ===")
        all_reqs.clear()
        result3 = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            var ec = window.emconfig;
            if (!ec.RequestJsonp) { resolve({error: 'no RequestJsonp'}); return; }
            try {
                ec.RequestJsonp({
                    url: "rtV1",
                    type: "rt_get_rank",
                    data: {rankType: "10004", recIdx: "0", recCnt: "3", rankid: "0", appVer: "9001000"},
                    success: function(t) { resolve({ok: true, preview: String(t).slice(0, 300)}); },
                    error: function(e) { resolve({error: String(e)}); }
                });
            } catch(e) { resolve({exception: e.message}); }
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("Result: %s" % result3)
        print("Requests: %d" % len(all_reqs))
        for r in all_reqs[:5]:
            print("  %s %s" % (r["method"], r["url"][:150]))

        await browser.close()

asyncio.run(main())
