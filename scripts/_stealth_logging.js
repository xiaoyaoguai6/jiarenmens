// === Block navigation triggered by app-gate dialog callbacks ===
// The site emDialog.emConfirm dismiss-callback calls history.back() to
// redirect away. We neutralize history.back() so the page stays put.
// (Note: window.location cannot be redefined in browsers, so we only
//  block history.back() here; dialog auto-dismiss handles the rest.)
(function() {
    try {
        window.history.back = function() {
            console.log("[stealth] blocked history.back()");
        };
        // Also block history.go(-1) which is equivalent
        var __origGo = window.history.go.bind(window.history);
        window.history.go = function(delta) {
            if (delta === -1) {
                console.log("[stealth] blocked history.go(-1)");
                return;
            }
            __origGo(delta);
        };
    } catch(e) {
        console.log("[stealth] history override error:", e);
    }
})();

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

// === emBridge (MUST return valid JSON for GetCurrentUser / GetUserAutoLogin) ===
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

// === Dialog dismissal (HIDE instead of clicking cancel) ===
// Clicking cancel triggers history.back() in the site's callback,
// so we just hide the dialog and mask via CSS.
function __dismissDialog() {
    var hideSelectors = [
        ".confirm", ".alert", ".mask", ".dialog",
        "[class*=\"confirm\"]", "[class*=\"dialog-mask\"]", "[class*=\"mask\"]",
        ".em-dialog", ".em-mask",
    ];
    var anyHidden = false;
    for (var k = 0; k < hideSelectors.length; k++) {
        try {
            var el = document.querySelectorAll(hideSelectors[k]);
            for (var j = 0; j < el.length; j++) {
                if (el[j] && el[j].offsetParent !== null && el[j].style.display !== "none") {
                    el[j].style.display = "none";
                    anyHidden = true;
                }
            }
        } catch(e) {}
    }
    if (anyHidden) console.log("[stealth] hid app-gate dialog(s)");
    return anyHidden;
}

function __startObserver() {
    if (!document.body) { setTimeout(__startObserver, 100); return; }
    try {
        new MutationObserver(function(mutations) {
            var hasNewNodes = false;
            for (var i = 0; i < mutations.length; i++) {
                if (mutations[i].addedNodes.length > 0) { hasNewNodes = true; break; }
            }
            if (hasNewNodes) __dismissDialog();
        }).observe(document.body, {childList: true, subtree: true});
        console.log("[stealth] MutationObserver started on document.body");
    } catch(e) { console.log("[stealth] Observer start error:", e); }
}
__startObserver();

var __dt = [300, 600, 1000, 1500, 2500, 4000, 6000, 10000];
for (var n = 0; n < __dt.length; n++) { setTimeout(__dismissDialog, __dt[n]); }

// === Log bridge calls ===
(function() {
    var _logCall = function(name, method, args) {
        console.log("[BRIDGE-LOG] " + name + "." + method + "(" + JSON.stringify(args).slice(0, 200) + ")");
    };
    
    // Override EMRead to log calls
    var _origEMRead = window.EMRead;
    Object.defineProperty(window, "EMRead", {
        get: function() {
            return new Proxy(_origEMRead, {
                get: function(t, k) {
                    if (k === "toJSON" || k === Symbol.toPrimitive) return undefined;
                    return function() {
                        _logCall("EMRead", String(k), Array.from(arguments));
                        return (t[k] || __stubFn).apply(t, arguments);
                    };
                }
            });
        },
        configurable: true
    });
    
    // Also log emh5, EMProjJs, emjs calls
    ["emh5","EMProjJs","emjs"].forEach(function(name) {
        var orig = window[name];
        if (orig) {
            Object.defineProperty(window, name, {
                get: function() {
                    return new Proxy(orig, {
                        get: function(t, k) {
                            if (k === "toJSON" || k === Symbol.toPrimitive) return undefined;
                            return function() {
                                _logCall(name, String(k), Array.from(arguments));
                                return (t[k] || __stubFn).apply(t, arguments);
                            };
                        }
                    });
                },
                configurable: true
            });
        }
    });
})();
