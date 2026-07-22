"""Diagnostic v3: test Object.defineProperty with configurable:false"""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from src.config import USER_AGENT

DEFINE_PROP_STEALTH = """
// === Anti-detection ===
Object.defineProperty(navigator, "webdriver", { get: function() { return undefined; } });
Object.defineProperty(navigator, "languages", { get: function() { return ["zh-CN", "zh", "en"]; } });

function __stubFn() { return "0"; }
function __mkBridge() {
    return new Proxy({}, {
        get: function(t, k) { if (k==="toJSON"||k===Symbol.toPrimitive) return undefined; return t[k]||__stubFn; },
        set: function(t, k, v) { t[k]=v; return true; }
    });
}

// === Runtime / Type ===
window.emRuntime = { InApp: true, InIOSApp: true, InAndroidApp: false, InHarmonyApp: false, OS: "iOS", AppVersion: "13.5.0", DeviceId: "DCB485C9C5E69EC1543FC90B84C6EBFA" };
window.emType = { OSType: { Android: 1, iOS: 2, HarmonyOS: 3 } };

// === Utility ===
window.emUtility = new Proxy({
    getCookie: function(n) { return ""; },
    getUrlPar: function(n) { return ""; },
    weixinShareInit: function(o) {}
}, {
    get: function(t, k) { if (k in t) return t[k]; return __stubFn; },
    set: function(t, k, v) { t[k]=v; return true; }
});

// === Bridge objects (emh5 etc) - let page fully own these ===
window.emh5 = __mkBridge();
window.EMProjJs = __mkBridge();
window.EMRead = __mkBridge();
window.emjs = __mkBridge();

// === emBridge ===
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

// === emconfig: Object.defineProperty with configurable:false ===
// Internal target holds our stubs + page-overwritten props
var __emconfTarget = {
    Request: {
        api001: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/rtV1";
            var data = opts.data || {};
            var parts = [];
            for (var k in data) { if (data.hasOwnProperty(k)) parts.push(encodeURIComponent(k)+"="+encodeURIComponent(data[k])); }
            console.log("[stealth] api001:", opts.type, JSON.stringify(opts.data).slice(0,150));
            fetch(url + (parts.length ? "?"+parts.join("&") : ""))
                .then(function(r){return r.text()})
                .then(function(t){ if(opts.success) opts.success(t); })
                .catch(function(e){ if(opts.error) opts.error(String(e)); });
        },
        api003: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson";
            var opdata = opts.data || {};
            var body = [];
            for (var k in opdata) { if (opdata.hasOwnProperty(k)) {
                var v = opdata[k];
                body.push(encodeURIComponent(k)+"="+encodeURIComponent(typeof v==="object"?JSON.stringify(v):v));
            }}
            console.log("[stealth] api003:", JSON.stringify(opts.data).slice(0,150));
            fetch(url, {method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.join("&")})
                .then(function(r){return r.text()})
                .then(function(t){ if(opts.success) opts.success(t); })
                .catch(function(e){ if(opts.error) opts.error(String(e)); });
        }
    }
};

// The proxy that the page reads
var __emconfProxy = new Proxy(__emconfTarget, {
    set: function(t, k, v) {
        // If page sets Request, merge its extra methods (keep our api001/api003)
        if (k === "Request" && v && typeof v === "object") {
            Object.keys(v).forEach(function(kk) {
                if (kk !== "api001" && kk !== "api003") { t.Request[kk] = v[kk]; }
            });
            return true;
        }
        t[k] = v;
        return true;
    },
    get: function(t, k) {
        if (k === "toJSON" || k === Symbol.toPrimitive) return undefined;
        return t[k];
    }
});

// Lock window.emconfig so page CANNOT replace it
Object.defineProperty(window, "emconfig", {
    get: function() { return __emconfProxy; },
    set: function(v) {
        // Merge any properties the page tries to set on window.emconfig
        if (v && typeof v === "object") {
            Object.keys(v).forEach(function(k) {
                if (k === "Request" && v[k] && typeof v[k] === "object") {
                    Object.keys(v[k]).forEach(function(kk) {
                        if (kk !== "api001" && kk !== "api003") { __emconfTarget.Request[kk] = v[k][kk]; }
                    });
                } else {
                    __emconfTarget[k] = v[k];
                }
            });
        }
        // Return true to allow the assignment (though get will still return our proxy)
    },
    configurable: false,
    enumerable: true
});

// === Dialog dismissal as fallback ===
function __dismiss() {
    var btn = document.querySelector("[id*='confirm_cancel']");
    if (btn && btn.offsetParent) { btn.click(); console.log("[stealth] dialog dismissed"); return true; }
    return false;
}
(function __obs(){
    if (!document.body) { setTimeout(__obs, 100); return; }
    try { new MutationObserver(function(){__dismiss()}).observe(document.body, {childList:true, subtree:true}); } catch(e) {}
})();
for (var n=300; n<20000; n+=500) setTimeout(__dismiss, n);
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
        await ctx.add_init_script(DEFINE_PROP_STEALTH)
        page = await ctx.new_page()

        logs = []
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text[:400]}"))
        page.on("pageerror", lambda e: logs.append(f"[PAGE_ERR] {e}"))
        
        api_requests = []
        page.on("request", lambda req: api_requests.append(f"> {req.method} {req.url[:300]}") if "dfcfs" in req.url or "emdcspzhapi" in req.url else None)
        page.on("response", lambda resp: api_requests.append(f"< {resp.status} {resp.url[:300]}") if "dfcfs" in resp.url or "emdcspzhapi" in resp.url else None)

        url = "https://groupwap.eastmoney.com/group/reality/info.html?zh=900113132"
        print(f"Opening: {url}")
        resp = await page.goto(url, wait_until="load", timeout=30000)
        print(f"Status: {resp.status}")
        await asyncio.sleep(15)

        body = await page.evaluate("document.body ? document.body.innerHTML.slice(0, 3000) : 'NO BODY'")
        div_count = await page.evaluate("document.querySelectorAll('div').length")
        detail = await page.evaluate("""() => { var el = document.querySelector('#detail-content'); return el ? el.innerHTML.slice(0, 500) : 'NOT FOUND'; }""")
        confirm_el = await page.evaluate("""() => { var el = document.querySelector('.confirm'); return el ? 'display:' + window.getComputedStyle(el).display + ' top:' + el.style.top : 'NOT FOUND'; }""")
        emconfig_info = await page.evaluate("""() => { try { var ec = window.emconfig; return JSON.stringify({hasReq:!!ec.Request, api001:typeof(ec.Request&&ec.Request.api001), isBuildRelease:ec.isBuildRelease}); } catch(e) { return 'ERR:'+e.message; } }""")

        print(f"\nDivs: {div_count}")
        print(f"#detail-content: \"{detail[:200]}\"")
        print(f"Confirm: {confirm_el}")
        print(f"emconfig: {emconfig_info}")
        print(f"\nBody (first 3000):\n{body[:3000]}")

        api_logs = [l for l in logs if any(k in l for k in ["api001","api003","stealth","emRead","PAGE_ERR","dialog"])]
        print(f"\n--- Relevant console ({len(api_logs)}/{len(logs)}) ---")
        for l in api_logs[:50]:
            print(l)
        
        print(f"\n--- API requests ({len(api_requests)}) ---")
        for r in api_requests:
            print(r)
        
        await browser.close()

asyncio.run(main())
