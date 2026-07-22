import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from src.config import USER_AGENT

STEALTH = """
// Standard stealth + override emDialog.emConfirm to be a NO-OP that doesn't block
Object.defineProperty(navigator, "webdriver", { get: function() { return undefined; } });
Object.defineProperty(navigator, "languages", { get: function() { return ["zh-CN", "zh", "en"]; } });

function __stubFn() { return "0"; }
function __mkBridge() {
    return new Proxy({}, {
        get: function(t, k) { if (k === "toJSON" || k === Symbol.toPrimitive) return undefined; return t[k] || __stubFn; },
        set: function(t, k, v) { t[k] = v; return true; }
    });
}

window.emRuntime = {
    InApp: true, InIOSApp: true, InAndroidApp: false, InHarmonyApp: false,
    OS: "iOS", AppVersion: "13.5.0", DeviceId: "DCB485C9C5E69EC1543FC90B84C6EBFA",
    AppName: "东方财富"
};
window.emType = { OSType: { Android: 1, iOS: 2, HarmonyOS: 3 } };
window.emUtility = {
    getCookie: function() { return ""; },
    getUrlPar: function() { return ""; },
    weixinShareInit: function() {},
};
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
    get: function(t, k) { if (k === "toJSON" || k === Symbol.toPrimitive) return undefined; return t[k] || __stubFn; },
    set: function(t, k, v) { t[k] = v; return true; }
});

// emconfig with working api001/api003 bridges
var __emconfTarget = {
    Request: {
        api001: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/rtV1";
            var data = opts.data || {};
            var parts = [];
            for (var k in data) {
                if (data.hasOwnProperty(k)) {
                    parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(data[k]));
                }
            }
            parts.push("type=" + encodeURIComponent(opts.type || "get"));
            var fullUrl = url + (parts.length ? "?" + parts.join("&") : "");
            console.log("[stealth] api001 URL:", fullUrl);
            fetch(fullUrl)
                .then(function(r) { return r.text(); })
                .then(function(t) {
                    console.log("[stealth] api001 OK, len:", t.length, "preview:", t.slice(0, 200));
                    if (opts.success) opts.success(t);
                })
                .catch(function(e) { console.log("[stealth] api001 ERR:", e); if (opts.error) opts.error(String(e)); });
        },
        api003: function(opts) {
            var url = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson";
            var opdata = opts.data || {};
            var body = [];
            for (var k in opdata) {
                if (opdata.hasOwnProperty(k)) {
                    var v = opdata[k];
                    body.push(encodeURIComponent(k) + "=" + encodeURIComponent(typeof v === "object" ? JSON.stringify(v) : v));
                }
            }
            console.log("[stealth] api003 URL:", url, "body:", body.join("&").slice(0, 200));
            fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: body.join("&")
            })
                .then(function(r) { return r.text(); })
                .then(function(t) {
                    console.log("[stealth] api003 OK, len:", t.length, "preview:", t.slice(0, 200));
                    if (opts.success) opts.success(t);
                })
                .catch(function(e) { console.log("[stealth] api003 ERR:", e); if (opts.error) opts.error(String(e)); });
        }
    }
};

Object.defineProperty(window, "emconfig", {
    get: function() { return __emconfTarget; },
    set: function(v) {
        if (v && typeof v === "object") {
            Object.keys(v).forEach(function(k) {
                if (k === "Request" && v[k] && typeof v[k] === "object") {
                    Object.keys(v[k]).forEach(function(kk) {
                        if (kk !== "api001" && kk !== "api003") { __emconfTarget.Request[kk] = v[k][kk]; }
                    });
                } else { __emconfTarget[k] = v[k]; }
            });
        }
    },
    configurable: false, enumerable: true
});

// CRITICAL: Override emDialog.emConfirm to be a no-op
// We need to wait for vendor.js to define emDialog first, then override
var __origEmConfirm = null;
Object.defineProperty(window, "__emDialogOverridden", { value: false, writable: true });

// Use a MutationObserver to detect when emDialog.emConfirm becomes available
(function __overrideDialog() {
    if (window.emDialog && window.emDialog.emConfirm) {
        if (!window.__emDialogOverridden) {
            __origEmConfirm = window.emDialog.emConfirm;
            window.emDialog.emConfirm = function(opts) {
                console.log("[stealth] emDialog.emConfirm intercepted, content:", (opts && opts.content || "").slice(0, 50));
                // DON'T show the dialog, just log it
                // If there's a callback for cancel, call it so the page continues
                if (opts && opts.callback) {
                    console.log("[stealth] auto-clicking cancel");
                    opts.callback("cancel");
                }
            };
            window.__emDialogOverridden = true;
            console.log("[stealth] emDialog.emConfirm overridden");
        }
    } else {
        setTimeout(__overrideDialog, 100);
    }
})();
"""

async def main():
    zh_id = sys.argv[1] if len(sys.argv) > 1 else "900113132"

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
        page.on("console", lambda m: logs.append("[{}] {}".format(m.type, m.text[:400])))

        url = "https://groupwap.eastmoney.com/group/reality/info.html?zh={}".format(zh_id)
        print("Loading: {}".format(url))
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(10)
        print("Page loaded. {} console messages.".format(len(logs)))

        # Show relevant logs
        relevant = [l for l in logs if any(k in l for k in ["stealth", "api001", "api003", "emRead", "emDialog", "emconfig"])]
        print("\n--- Relevant console ---")
        for l in relevant[-30:]:
            print(l)

        # Now try to call the API from JS context with various parameters
        print("\n=== Trying to call API from page context ===")
        
        # Try various API calls
        test_calls = [
            {"type": "rt_get_info", "data": {"zh": zh_id, "appVer": "9001000"}},
            {"type": "rt_get_userinfo", "data": {"zh": zh_id, "appVer": "9001000"}},
            {"type": "rt_get_position", "data": {"zh": zh_id, "appVer": "9001000"}},
            {"type": "rt_get_change", "data": {"zh": zh_id, "appVer": "9001000"}},
        ]
        
        for tc in test_calls:
            result = await page.evaluate("""
                (function() {
                    return new Promise(function(resolve) {
                        var data = """ + json.dumps(tc["data"]) + """;
                        var type = """ + json.dumps(tc["type"]) + """;
                        if (!window.emconfig || !window.emconfig.Request || !window.emconfig.Request.api001) {
                            resolve({error: "emconfig.Request.api001 not available"});
                            return;
                        }
                        window.emconfig.Request.api001({
                            url: "rtV1",
                            type: type,
                            data: data,
                            success: function(t) {
                                resolve({success: true, data: t.slice(0, 500)});
                            },
                            error: function(t) {
                                resolve({error: String(t)});
                            }
                        });
                    });
                })()
            """)
            print("  type={}: {}".format(tc["type"], json.dumps(result, ensure_ascii=False)[:300]))

        # Try api003 calls
        print("\n=== Trying api003 calls ===")
        api003_calls = [
            {"path": "zuheV64/JS.aspx", "pageUrl": url, "urlParm": {"zh": zh_id}},
            {"path": "zuheV64/JS.aspx", "pageUrl": url, "urlParm": {"zjzh": zh_id}},
            {"path": "zuheV64/JS.aspx", "pageUrl": url, "urlParm": {"type": "get_zjzh", "zjzh": zh_id}},
        ]
        for tc in api003_calls:
            result = await page.evaluate("""
                (function() {
                    return new Promise(function(resolve) {
                        var data = """ + json.dumps(tc) + """;
                        if (!window.emconfig || !window.emconfig.Request || !window.emconfig.Request.api003) {
                            resolve({error: "emconfig.Request.api003 not available"});
                            return;
                        }
                        window.emconfig.Request.api003({
                            url: "apistock/tran/getJson",
                            type: "post",
                            data: data,
                            success: function(t) {
                                resolve({success: true, data: t.slice(0, 500)});
                            },
                            error: function(t) {
                                resolve({error: String(t)});
                            }
                        });
                    });
                })()
            """)
            print("  data={}: {}".format(json.dumps(tc, ensure_ascii=False)[:100], json.dumps(result, ensure_ascii=False)[:300]))

        await browser.close()

asyncio.run(main())
