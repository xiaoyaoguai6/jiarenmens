import re
from pathlib import Path

filepath = Path(r"D:\project\jiarenmens\src\utils\async_playwright_pool.py")
content = filepath.read_text(encoding="utf-8")

start_marker = "_STEALTH_SCRIPT = "
start_idx = content.index(start_marker) + len(start_marker)
start_idx += 3

end_marker = '\n"""\n    async def _create_context'
end_idx = content.index(end_marker, start_idx)

# Separately define the new stealth JS as a raw string
new_stealth_js = '''    // Anti-detection + EastMoney APP webview bridge emulation
    _STEALTH_SCRIPT = """
    // === WebDriver / anti-detection ===
    Object.defineProperty(navigator, "webdriver", { get: () => undefined });
    Object.defineProperty(navigator, "languages", { get: () => ["zh-CN", "zh", "en"] });
    var __origQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (__origQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters && parameters.name === "notifications"
                ? Promise.resolve({ state: Notification.permission })
                : __origQuery(parameters)
        );
    }

    // === Stub helpers ===
    function __stubFn() { return "0"; }
    function __mkBridge() {
        return new Proxy({}, {
            get: function(t, k) { if (k==="toJSON"||k===Symbol.toPrimitive) return undefined; return t[k]||__stubFn; },
            set: function(t, k, v) { t[k]=v; return true; }
        });
    }

    // === emRuntime / emType ===
    window.emRuntime = {
        InApp: true, InIOSApp: true, InAndroidApp: false, InHarmonyApp: false,
        OS: "iOS", AppVersion: "13.5.0", DeviceId: "DCB485C9C5E69EC1543FC90B84C6EBFA",
    };
    window.emType = { OSType: { Android: 1, iOS: 2, HarmonyOS: 3 } };

    // === emUtility ===
    window.emUtility = {
        getCookie: function(name) { return ""; },
        getUrlPar: function(name) { return ""; },
        weixinShareInit: function(opts) {},
    };

    // === emh5, EMProjJs, EMRead, emjs ===
    window.emh5 = __mkBridge();
    window.EMProjJs = __mkBridge();
    window.EMRead = __mkBridge();
    window.emjs = __mkBridge();

    // === emBridge (MUST return valid JSON) ===
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

    // === emconfig.Request replacement (native bridge -> real fetch) ===
    (function() {
        var SHIPAN_URL = "https://emdcspzhapi.dfcfs.cn/rtV1";
        var PROXY_URL  = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson";

        function __api001(opts) {
            var data = opts.data || {};
            var parts = [];
            for (var k in data) { if (data.hasOwnProperty(k)) parts.push(encodeURIComponent(k)+"="+encodeURIComponent(data[k])); }
            fetch(SHIPAN_URL + (parts.length ? "?"+parts.join("&") : ""))
                .then(function(r){return r.text()}).then(function(t){if(opts.success)opts.success(t)})
                .catch(function(e){console.log("[stealth] api001 err:",e);if(opts.error)opts.error(String(e))});
        }
        function __api003(opts) {
            var opdata = opts.data || {};
            var body = [];
            for (var k in opdata) { if (opdata.hasOwnProperty(k)) {
                var v = opdata[k];
                body.push(encodeURIComponent(k)+"="+encodeURIComponent(typeof v==="object"?JSON.stringify(v):v));
            }}
            fetch(PROXY_URL, {method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.join("&")})
                .then(function(r){return r.text()}).then(function(t){if(opts.success)opts.success(t)})
                .catch(function(e){console.log("[stealth] api003 err:",e);if(opts.error)opts.error(String(e))});
        }

        var __reqTarget = { api001: __api001, api003: __api003 };
        var __reqProxy = new Proxy(__reqTarget, {
            set: function(t,k,v) { if (k==="api001"||k==="api003") return true; t[k]=v; return true; }
        });
        var __emconfTarget = { Request: __reqProxy };
        var __emconfProxy = new Proxy(__emconfTarget, {
            set: function(t,k,v) {
                if (k==="Request"&&v&&typeof v==="object") {
                    Object.keys(v).forEach(function(kk){if(kk!=="api001"&&kk!=="api003")__reqTarget[kk]=v[kk]});
                    return true;
                }
                t[k]=v; return true;
            }
        });
        Object.defineProperty(window, "emconfig", {
            get: function(){return __emconfProxy},
            set: function(v) {
                if (v&&typeof v==="object") {
                    Object.keys(v).forEach(function(k){
                        if (k==="Request"&&v[k]&&typeof v[k]==="object") {
                            Object.keys(v[k]).forEach(function(kk){if(kk!=="api001"&&kk!=="api003")__reqTarget[kk]=v[k][kk]});
                        } else { __emconfTarget[k]=v[k]; }
                    });
                }
            },
            configurable:true, enumerable:true
        });
    })();

    // === Dialog dismissal ===
    function __dismissDialog() {
        var cancelSelectors = [
            "[id*=\"confirm_cancel\"]",
            ".confirm-cancel",
            ".dialog-cancel",
            ".cancel-btn",
            "[class*=\"cancel\"]",
        ];
        for (var i = 0; i < cancelSelectors.length; i++) {
            try {
                var el = document.querySelector(cancelSelectors[i]);
                if (el && el.offsetParent !== null) { el.click(); return true; }
            } catch(e) {}
        }
        var allDivs = document.querySelectorAll(".confirm div, .alert div, .dialog div, .mask div, [class*=\"confirm\"] div, [class*=\"dialog\"] div");
        for (var j = 0; j < allDivs.length; j++) {
            var dv = allDivs[j];
            if (dv.textContent && dv.textContent.indexOf(String.fromCharCode(28040))>=0) { try{dv.click()}catch(e){} return true; }
        }
        var hideSelectors = [".confirm", ".alert", ".mask", ".dialog", "[class*=\"confirm\"]", "[class*=\"dialog-mask\"]"];
        for (var k = 0; k < hideSelectors.length; k++) {
            try {
                var el2 = document.querySelector(hideSelectors[k]);
                if (el2 && el2.offsetParent !== null && el2.style) { el2.style.display="none"; return true; }
            } catch(e) {}
        }
        return false;
    }

    function __startObserver() {
        if (!document.body) { setTimeout(__startObserver, 100); return; }
        try { new MutationObserver(function(){__dismissDialog()}).observe(document.body,{childList:true,subtree:true}); } catch(e) {}
    }
    __startObserver();

    var __dt = [300,600,1000,1500,2500,4000,6000,10000];
    for (var n=0; n<__dt.length; n++) { setTimeout(__dismissDialog, __dt[n]); }
"""'''

new_content = content[:start_idx] + new_stealth_js + content[end_idx:]
filepath.write_text(new_content, encoding="utf-8")
print("STEALTH_SCRIPT replaced successfully")
print(f"New file size: {filepath.stat().st_size} bytes")
