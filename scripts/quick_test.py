import sys, asyncio, json
from pathlib import Path
sys.path.insert(0, r'D:\project\jiarenmens')

from playwright.async_api import async_playwright
from src.config import USER_AGENT, MOBILE_VIEWPORT, DEVICE_SCALE_FACTOR

# Simplified stealth - just bridge objects, let the page control everything
SIMPLE_STEALTH = '''
// Anti-detection basics
Object.defineProperty(navigator, "webdriver", { get: () => undefined });
Object.defineProperty(navigator, "languages", { get: () => ["zh-CN", "zh", "en"] });

// Bridge stubs - allow full replacement by page
function __mkBridge() {
    var stub = function() { return "0"; };
    return new Proxy({}, {
        get: function(t, k) { if (k==="toJSON"||k===Symbol.toPrimitive) return undefined; return t[k]||stub; },
        set: function(t, k, v) { t[k]=v; return true; }
    });
}

// App environment
window.emRuntime = { InApp: true, InIOSApp: true, InAndroidApp: false, InHarmonyApp: false, OS: "iOS", AppVersion: "13.5.0", DeviceId: "DCB485C9C5E69EC1543FC90B84C6EBFA" };
window.emType = { OSType: { Android: 1, iOS: 2, HarmonyOS: 3 } };
window.emUtility = { getCookie: function(n) { return ""; }, getUrlPar: function(n) { return ""; }, weixinShareInit: function(o) {} };

// Bridge objs
window.emh5 = __mkBridge();
window.EMProjJs = __mkBridge();
window.EMRead = __mkBridge();
window.emjs = __mkBridge();

// emBridge with user data
window.emBridge = __mkBridge();
window.emBridge.GetCurrentUser = function(cb) { if(typeof cb==="function"){try{cb(JSON.stringify({data:{uid:""}}));}catch(e){}} return "0"; };
window.emBridge.GetUserAutoLogin = function(cb) { if(typeof cb==="function"){try{cb(JSON.stringify({ct:"",ut:"",uid:""}));}catch(e){}} return "0"; };
window.emBridge.call = function() { return "0"; };

// emconfig: FULLY replaceable by the page, with api001/api003 as REAL fetch stubs
window.__emconfig_real = {
    isBuildRelease: true,
    dsn: "",
    pkgName: "shipan",
    buildTime: "2025",
    buildDate: "2025-01-01",
    emglbaljs_version: "1.0.0",
    Request: {
        api001: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/rtV1";
            var data = opts.data || {};
            var parts = [];
            for (var k in data) { if (data.hasOwnProperty(k)) parts.push(encodeURIComponent(k)+"="+encodeURIComponent(data[k])); }
            console.log("[stealth] api001 call:", url, opts.type, JSON.stringify(opts.data).slice(0,200));
            fetch(url + (parts.length ? "?"+parts.join("&") : ""))
                .then(function(r){return r.text()})
                .then(function(t){
                    console.log("[stealth] api001 success, len:", t.length);
                    if(opts.success) opts.success(t);
                })
                .catch(function(e){
                    console.log("[stealth] api001 err:", e);
                    if(opts.error) opts.error(String(e));
                });
        },
        api003: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson";
            var opdata = opts.data || {};
            var body = [];
            for (var k in opdata) { if (opdata.hasOwnProperty(k)) {
                var v = opdata[k];
                body.push(encodeURIComponent(k)+"="+encodeURIComponent(typeof v==="object"?JSON.stringify(v):v));
            }}
            console.log("[stealth] api003 call:", url, JSON.stringify(opts.data).slice(0,200));
            fetch(url, {method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.join("&")})
                .then(function(r){return r.text()})
                .then(function(t){
                    console.log("[stealth] api003 success, len:", t.length);
                    if(opts.success) opts.success(t);
                })
                .catch(function(e){
                    console.log("[stealth] api003 err:", e);
                    if(opts.error) opts.error(String(e));
                });
        }
    }
};
window.emconfig = new Proxy(window.__emconfig_real, {
    set: function(t, k, v) { t[k]=v; return true; },
    get: function(t, k) { return t[k]; }
});
''';

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        ctx = await browser.new_context(
            viewport=MOBILE_VIEWPORT, user_agent=USER_AGENT,
            locale='zh-CN', timezone_id='Asia/Shanghai',
            has_touch=True, is_mobile=True, device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        await ctx.add_init_script(SIMPLE_STEALTH)
        page = await ctx.new_page()
        
        network = []
        page.on('request', lambda r: network.append(f'> {r.method} {r.url[:300]}'))
        page.on('requestfailed', lambda r: network.append(f'X {r.url[:300]} - {r.failure}'))
        page.on('response', lambda r: network.append(f'<{r.status} {r.url[:300]}'))
        
        console_all = []
        page.on('console', lambda m: console_all.append(f'[{m.type}] {m.text[:500]}'))
        page.on('pageerror', lambda e: console_all.append(f'[PAGE_ERR] {e}'))
        
        url = 'https://groupwap.eastmoney.com/group/reality/info.html?zh=900113132'
        print(f'Opening: {url}')
        resp = await page.goto(url, wait_until='load', timeout=30000)
        print(f'Status: {resp.status}')
        await asyncio.sleep(10)
        
        body = await page.evaluate('document.body ? document.body.innerHTML.slice(0, 1500) : "NONE"')
        print(f'Body (first 1500): {body[:1500]}')
        
        divs = await page.evaluate('document.querySelectorAll("div").length')
        print(f'Divs: {divs}')
        
        print(f'\n--- Console ({len(console_all)}) ---')
        for c in console_all[:30]:
            print(c[:500])
        
        print(f'\n--- Network filtered ---')
        api_requests = [n for n in network if 'emdcspzhapi' in n or 'apistock' in n or 'stealth' in n.lower()]
        for n in api_requests:
            print(n[:300])
        print(f'Total network entries: {len(network)}, API entries: {len(api_requests)}')
        
        await browser.close()

asyncio.run(main())
