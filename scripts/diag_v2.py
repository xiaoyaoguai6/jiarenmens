"""Diagnostic v2: test hybrid stealth"""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from src.config import USER_AGENT

HYBRID_STEALTH = """
Object.defineProperty(navigator, "webdriver", { get: function() { return undefined; } });
Object.defineProperty(navigator, "languages", { get: function() { return ["zh-CN", "zh", "en"]; } });

function __stubFn() { return "0"; }
function __mkBridge() {
    return new Proxy({}, {
        get: function(t, k) { if (k==="toJSON"||k===Symbol.toPrimitive) return undefined; return t[k]||__stubFn; },
        set: function(t, k, v) { t[k]=v; return true; }
    });
}

window.emRuntime = { InApp: true, InIOSApp: true, InAndroidApp: false, InHarmonyApp: false, OS: "iOS", AppVersion: "13.5.0", DeviceId: "DCB485C9C5E69EC1543FC90B84C6EBFA" };
window.emType = { OSType: { Android: 1, iOS: 2, HarmonyOS: 3 } };
window.emUtility = { getCookie: function(n) { return ""; }, getUrlPar: function(n) { return ""; }, weixinShareInit: function(o) {} };

window.emh5 = __mkBridge();
window.EMProjJs = __mkBridge();
window.EMRead = __mkBridge();
window.emjs = __mkBridge();

window.emBridge = new Proxy({
    GetCurrentUser: function(cb) {
        if (typeof cb === "function") { try { cb(JSON.stringify({data:{uid:""}})); } catch(e) {} }
        return "0";
    },
    GetUserAutoLogin: function(cb) {
        if (typeof cb === "function") { try { cb(JSON.stringify({ct:"",ut:"",uid:""})); } catch(e) {} }
        return "0";
    },
    call: function() { return "0"; },
}, {
    get: function(t, k) { if (k==="toJSON"||k===Symbol.toPrimitive) return undefined; return t[k]||__stubFn; },
    set: function(t, k, v) { t[k]=v; return true; }
});

window.__emconfig_real = {
    isBuildRelease: true, dsn: "", pkgName: "shipan", buildTime: "2025", buildDate: "2025-01-01", emglbaljs_version: "1.0.0",
    Request: {
        api001: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/rtV1";
            var data = opts.data || {};
            var parts = [];
            for (var k in data) { if (data.hasOwnProperty(k)) parts.push(encodeURIComponent(k)+"="+encodeURIComponent(data[k])); }
            console.log("[stealth] api001 CALL:", opts.type, JSON.stringify(opts.data).slice(0,200));
            fetch(url + (parts.length ? "?"+parts.join("&") : ""))
                .then(function(r){return r.text()}).then(function(t){
                    console.log("[stealth] api001 OK, len:", t.length);
                    if(opts.success) opts.success(t);
                }).catch(function(e){console.log("[stealth] api001 ERR:",e);if(opts.error)opts.error(String(e));});
        },
        api003: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson";
            var opdata = opts.data || {};
            var body = [];
            for (var k in opdata) { if (opdata.hasOwnProperty(k)) {
                var v = opdata[k];
                body.push(encodeURIComponent(k)+"="+encodeURIComponent(typeof v==="object"?JSON.stringify(v):v));
            }}
            console.log("[stealth] api003 CALL:", JSON.stringify(opts.data).slice(0,200));
            fetch(url, {method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.join("&")})
                .then(function(r){return r.text()}).then(function(t){
                    console.log("[stealth] api003 OK, len:", t.length);
                    if(opts.success) opts.success(t);
                }).catch(function(e){console.log("[stealth] api003 ERR:",e);if(opts.error)opts.error(String(e));});
        }
    }
};
window.emconfig = new Proxy(window.__emconfig_real, {
    set: function(t, k, v) { console.log("[stealth] emconfig.set:", k); t[k]=v; return true; },
    get: function(t, k) { return t[k]; }
});
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent=USER_AGENT,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            has_touch=True,
            is_mobile=True,
            device_scale_factor=3,
        )
        await ctx.add_init_script(HYBRID_STEALTH)
        page = await ctx.new_page()

        logs = []
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:400]}"))
        page.on("pageerror", lambda e: logs.append(f"[PAGE_ERR] {e}"))
        
        # Also track network requests to API
        api_requests = []
        def on_request(req):
            url = req.url
            if "dfcfs" in url or "emdcspzhapi" in url or "apistock" in url:
                api_requests.append(f"> {req.method} {url[:300]}")
        def on_response(resp):
            url = resp.url
            if "dfcfs" in url or "emdcspzhapi" in url or "apistock" in url:
                api_requests.append(f"< {resp.status} {url[:300]}")
        page.on("request", on_request)
        page.on("response", on_response)

        url = "https://groupwap.eastmoney.com/group/reality/info.html?zh=900113132"
        print(f"Opening: {url}")
        resp = await page.goto(url, wait_until="load", timeout=30000)
        print(f"Status: {resp.status}")
        await asyncio.sleep(15)

        body = await page.evaluate("document.body ? document.body.innerHTML.slice(0, 3000) : 'NO BODY'")
        div_count = await page.evaluate("document.querySelectorAll('div').length")
        detail = await page.evaluate("""() => { var el = document.querySelector('#detail-content'); return el ? el.innerHTML.slice(0, 500) : 'NOT FOUND'; }""")
        confirm_el = await page.evaluate("""() => { var el = document.querySelector('.confirm'); return el ? 'display:' + window.getComputedStyle(el).display + ' top:' + el.style.top : 'NOT FOUND'; }""")
        emconfig_info = await page.evaluate("""() => { try { var ec = window.emconfig; return JSON.stringify({isBuildRelease: ec.isBuildRelease, hasRequest: !!ec.Request, api001: typeof ec.Request.api001, keys: Object.keys(ec).slice(0,10)}); } catch(e) { return 'ERR:' + e.message; } }""")

        print(f"\nDivs: {div_count}")
        print(f"#detail-content: \"{detail[:200]}\"")
        print(f"Confirm: {confirm_el}")
        print(f"emconfig: {emconfig_info}")
        print(f"\nBody (first 3000):\n{body[:3000]}")

        api_logs = [l for l in logs if any(k in l for k in ["api001","api003","stealth","emRead","emconfig","PAGE_ERR","EMProj","InApp","set:"])]
        print(f"\n--- Relevant console ({len(api_logs)}/{len(logs)}) ---")
        for l in api_logs[:50]:
            print(l)
        
        print(f"\n--- API requests ({len(api_requests)}) ---")
        for r in api_requests:
            print(r)
        
        await browser.close()

asyncio.run(main())
