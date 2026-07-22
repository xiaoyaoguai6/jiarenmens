// === 东方财富 APP WebView 伪装脚本 ===
// 核心策略：拦截 emDialog.emConfirm 使其不弹窗、不触发 history.back()
// 然后让 emconfig.Request.api001 / api003 真正调用 API 获取数据

(function() {
    // ==================== 1. 阻止导航跳转 ====================
    try {
        window.history.back = function() { /* noop */ };
        var __origGo = window.history.go.bind(window.history);
        window.history.go = function(delta) {
            if (delta === -1) return;
            __origGo(delta);
        };
    } catch(e) {}

    // ==================== 2. WebDriver 反检测 ====================
    Object.defineProperty(navigator, "webdriver", { get: function() { return undefined; } });
    Object.defineProperty(navigator, "languages", { get: function() { return ["zh-CN", "zh", "en"]; } });

    // ==================== 3. 基础桥接对象 ====================
    function __stubFn() { return "0"; }
    function __mkBridge() {
        return new Proxy({}, {
            get: function(t, k) {
                if (k === "toJSON" || k === Symbol.toPrimitive) return undefined;
                return t[k] || __stubFn;
            },
            set: function(t, k, v) { t[k] = v; return true; }
        });
    }

    // emRuntime - 告诉页面"在 APP 内"
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

    // 原生桥接对象
    window.emh5 = __mkBridge();
    window.EMProjJs = __mkBridge();
    window.EMRead = __mkBridge();
    window.emjs = __mkBridge();

    // emBridge - 提供用户登录信息
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

    // ==================== 4. emconfig.Request 拦截 ====================
    // 拦截 emconfig 的设置，确保 api001/api003 始终可用
    var SHIPAN_URL = "https://emdcspzhapi.dfcfs.cn/rtV1";
    var PROXY_URL  = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson";

    function __api001(opts) {
        var data = opts.data || {};
        var parts = [];
        for (var k in data) { if (data.hasOwnProperty(k)) parts.push(encodeURIComponent(k)+"="+encodeURIComponent(data[k])); }
        var fullUrl = SHIPAN_URL + (parts.length ? "?"+parts.join("&") : "");
        fetch(fullUrl)
            .then(function(r){ return r.text(); })
            .then(function(t){ if(opts.success) opts.success(t); })
            .catch(function(e){ if(opts.error) opts.error(String(e)); });
    }

    function __api003(opts) {
        var opdata = opts.data || {};
        var body = [];
        for (var k in opdata) { if (opdata.hasOwnProperty(k)) {
            var v = opdata[k];
            body.push(encodeURIComponent(k)+"="+encodeURIComponent(typeof v==="object"?JSON.stringify(v):v));
        }}
        fetch(PROXY_URL, {method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.join("&")})
            .then(function(r){ return r.text(); })
            .then(function(t){ if(opts.success) opts.success(t); })
            .catch(function(e){ if(opts.error) opts.error(String(e)); });
    }

    // 创建 Request 代理：保护 api001/api003 不被页面覆盖，其他属性正常合并
    var __reqTarget = { api001: __api001, api003: __api003 };
    var __reqProxy = new Proxy(__reqTarget, {
        set: function(t, k, v) {
            // 阻止页面覆盖 api001/api003（页面版本使用原生桥接，不工作）
            if (k === "api001" || k === "api003") {
                return true; // 静默忽略
            }
            t[k] = v;
            return true;
        }
    });

    // 创建 emconfig 代理
    var __emconfTarget = { Request: __reqProxy };
    var __emconfProxy = new Proxy(__emconfTarget, {
        set: function(t, k, v) {
            if (k === "Request" && v && typeof v === "object") {
                // 页面设置 Request 时，合并属性但保护 api001/api003
                Object.keys(v).forEach(function(kk) {
                    if (kk !== "api001" && kk !== "api003") {
                        __reqTarget[kk] = v[kk];
                    }
                });
                return true;
            }
            t[k] = v;
            return true;
        }
    });

    // 定义 window.emconfig 为可拦截的属性
    Object.defineProperty(window, "emconfig", {
        get: function() { return __emconfProxy; },
        set: function(v) {
            if (v && typeof v === "object") {
                Object.keys(v).forEach(function(k) {
                    if (k === "Request" && v[k] && typeof v[k] === "object") {
                        Object.keys(v[k]).forEach(function(kk) {
                            // 保护 api001/api003 不被页面覆盖
                            if (kk !== "api001" && kk !== "api003") {
                                __reqTarget[kk] = v[k][kk];
                            }
                        });
                    } else {
                        __emconfTarget[k] = v[k];
                    }
                });
            }
        },
        configurable: true, enumerable: true
    });

    // ==================== 5. emDialog 拦截（关键！）====================
    // 直接拦截 emDialog.emConfirm，使其不弹窗、不触发回调
    // 这比隐藏 DOM 元素更可靠
    Object.defineProperty(window, "emDialog", {
        get: function() {
            return {
                emConfirm: function(opts) {
                    // 不弹窗、不触发回调（回调会调 history.back）
                },
                emAlert: function(opts) {},
                loading: function() {},
                removeLoading: function() {},
                success: function() {},
                alert: function() {},
                close: function() {}
            };
        },
        set: function() { /* 丢弃页面设置 */ },
        configurable: true, enumerable: true
    });

    // ==================== 6. 兜底：隐藏可能漏过的 dialog DOM ====================
    function __dismissDialog() {
        var sels = [
            ".confirm", ".alert", ".mask", ".dialog",
            "[class*='confirm']", "[class*='dialog-mask']", "[class*='mask']",
            ".em-dialog", ".em-mask"
        ];
        for (var k = 0; k < sels.length; k++) {
            try {
                var els = document.querySelectorAll(sels[k]);
                for (var j = 0; j < els.length; j++) {
                    if (els[j] && els[j].style) els[j].style.display = "none";
                }
            } catch(e) {}
        }
    }

    // MutationObserver 自动隐藏新出现的 dialog
    function __startObserver() {
        if (!document.body) { setTimeout(__startObserver, 100); return; }
        try {
            new MutationObserver(function() { __dismissDialog(); })
                .observe(document.body, {childList: true, subtree: true});
        } catch(e) {}
    }
    __startObserver();

    // 定时兜底
    var __dt = [200, 500, 1000, 2000, 3000, 5000];
    for (var n = 0; n < __dt.length; n++) { setTimeout(__dismissDialog, __dt[n]); }
})();
