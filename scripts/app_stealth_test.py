# -*- coding: utf-8 -*-
"""
完整反检测方案：伪装东方财富APP WebView访问H5页面

策略：
1. UA包含EMProjJs/EMRead关键字
2. 注入emh5/EMProjJs/EMRead桥接对象
3. 注入emconfig.Request.api001替换为fetch版本
4. 用Playwright route()代理API请求绕过CORS
5. 拦截emDialog阻止APP门控弹窗
"""
import sys, io, asyncio, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright
import requests as req_lib

# ==================== 配置 ====================
ZH_ID = "900023658"
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"

# 伪装为东方财富iPhone WebView
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

# 完整stealth脚本
STEALTH_JS = r"""
(function() {
    // ===== 1. 阻止导航跳转 =====
    try {
        window.history.back = function() {};
        var origGo = window.history.go.bind(window.history);
        window.history.go = function(delta) { if (delta !== -1) origGo(delta); };
    } catch(e) {}

    // ===== 2. WebDriver反检测 =====
    Object.defineProperty(navigator, "webdriver", { get: function() { return undefined; } });
    Object.defineProperty(navigator, "languages", { get: function() { return ["zh-CN", "zh", "en"]; } });

    // ===== 3. 基础桥接对象 =====
    function stubFn() { return "0"; }
    function mkBridge() {
        return new Proxy({}, {
            get: function(t, k) {
                if (k === "toJSON" || k === Symbol.toPrimitive) return undefined;
                return t[k] || stubFn;
            },
            set: function(t, k, v) { t[k] = v; return true; }
        });
    }

    // emRuntime - 告诉页面"在APP内"
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
    window.emh5 = mkBridge();
    window.EMProjJs = mkBridge();
    window.EMRead = mkBridge();
    window.emjs = mkBridge();

    // emBridge
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
        get: function(t, k) { if (k==="toJSON"||k===Symbol.toPrimitive) return undefined; return t[k]||stubFn; },
        set: function(t, k, v) { t[k]=v; return true; }
    });

    // ===== 4. emconfig.Request 拦截 =====
    var SHIPAN_URL = "https://emdcspzhapi.dfcfs.cn/rtV1";

    function api001Impl(opts) {
        var data = opts.data || {};
        var parts = [];
        for (var k in data) {
            if (data.hasOwnProperty(k))
                parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(data[k]));
        }
        var url = SHIPAN_URL + (parts.length ? "?" + parts.join("&") : "");
        console.log("[stealth] api001 fetch:", url.slice(0, 150));
        fetch(url)
            .then(function(r) { return r.text(); })
            .then(function(t) {
                console.log("[stealth] api001 success, len:", t.length);
                if (opts.success) opts.success(t);
            })
            .catch(function(e) {
                console.log("[stealth] api001 error:", e);
                if (opts.error) opts.error(String(e));
            });
    }

    function api003Impl(opts) {
        var opdata = opts.data || {};
        var body = [];
        for (var k in opdata) {
            if (opdata.hasOwnProperty(k)) {
                var v = opdata[k];
                body.push(encodeURIComponent(k) + "=" + encodeURIComponent(typeof v === "object" ? JSON.stringify(v) : v));
            }
        }
        fetch("https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson", {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded"},
            body: body.join("&")
        })
        .then(function(r) { return r.text(); })
        .then(function(t) { if (opts.success) opts.success(t); })
        .catch(function(e) { if (opts.error) opts.error(String(e)); });
    }

    // Request代理：保护api001/api003不被页面覆盖
    var reqTarget = { api001: api001Impl, api003: api003Impl };
    var reqProxy = new Proxy(reqTarget, {
        set: function(t, k, v) {
            if (k === "api001" || k === "api003") return true;
            t[k] = v;
            return true;
        }
    });

    // emconfig代理
    var emconfTarget = { Request: reqProxy };
    var emconfProxy = new Proxy(emconfTarget, {
        set: function(t, k, v) {
            if (k === "Request" && v && typeof v === "object") {
                Object.keys(v).forEach(function(kk) {
                    if (kk !== "api001" && kk !== "api003") reqTarget[kk] = v[kk];
                });
                return true;
            }
            t[k] = v;
            return true;
        }
    });

    Object.defineProperty(window, "emconfig", {
        get: function() { return emconfProxy; },
        set: function(v) {
            if (v && typeof v === "object") {
                Object.keys(v).forEach(function(k) {
                    if (k === "Request" && v[k] && typeof v[k] === "object") {
                        Object.keys(v[k]).forEach(function(kk) {
                            if (kk !== "api001" && kk !== "api003") reqTarget[kk] = v[k][kk];
                        });
                    } else {
                        emconfTarget[k] = v[k];
                    }
                });
            }
        },
        configurable: true, enumerable: true
    });

    // ===== 5. emDialog 拦截 =====
    Object.defineProperty(window, "emDialog", {
        get: function() {
            return {
                emConfirm: function(opts) {},
                emAlert: function(opts) {},
                loading: function() {},
                removeLoading: function() {},
                success: function() {},
                alert: function() {},
                close: function() {}
            };
        },
        set: function() {},
        configurable: true, enumerable: true
    });

    // ===== 6. 兜底隐藏dialog =====
    function dismissDialog() {
        var sels = [".confirm",".alert",".mask",".dialog","[class*='confirm']","[class*='dialog-mask']","[class*='mask']",".em-dialog",".em-mask"];
        for (var k = 0; k < sels.length; k++) {
            try {
                var els = document.querySelectorAll(sels[k]);
                for (var j = 0; j < els.length; j++) {
                    if (els[j] && els[j].style) els[j].style.display = "none";
                }
            } catch(e) {}
        }
    }
    function startObserver() {
        if (!document.body) { setTimeout(startObserver, 100); return; }
        try {
            new MutationObserver(function() { dismissDialog(); })
                .observe(document.body, {childList: true, subtree: true});
        } catch(e) {}
    }
    startObserver();
    var dt = [200, 500, 1000, 2000, 3000, 5000];
    for (var n = 0; n < dt.length; n++) { setTimeout(dismissDialog, dt[n]); }
})();
"""

# Python requests session for proxying
session = req_lib.Session()
session.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})


async def route_handler(route):
    """代理emdcspzhapi请求，绕过CORS"""
    url = route.request.url
    try:
        if route.request.method == "GET":
            resp = session.get(url, timeout=15)
        else:
            resp = session.post(url, data=route.request.post_data, timeout=15)
        await route.fulfill(
            status=resp.status_code,
            headers={"Content-Type": "application/json"},
            body=resp.text,
        )
    except Exception as e:
        await route.abort()


async def main():
    print("=" * 60)
    print("伪装APP WebView访问H5页面")
    print("=" * 60)
    print("ZH_ID: %s" % ZH_ID)
    print("URL: https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH_ID)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            executable_path=CHROME,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent=UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            has_touch=True,
            is_mobile=True,
            device_scale_factor=3,
        )
        await ctx.add_init_script(STEALTH_JS)
        page = await ctx.new_page()

        # 代理API请求
        await page.route("**/emdcspzhapi.dfcfs.cn/**", route_handler)

        # 捕获日志
        logs = []
        api_calls = []
        page.on("console", lambda m: logs.append("[%s] %s" % (m.type, m.text[:300])))
        page.on("console", lambda m: api_calls.append(m.text) if "api001" in m.text else None)

        # 加载页面
        print("\n加载页面中...")
        url = "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH_ID
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print("加载: %s" % str(e)[:80])

        await asyncio.sleep(8)

        # 获取页面内容
        body_text = await page.evaluate("document.body ? document.body.innerText : ''")
        print("\n===== 页面文本 =====")
        print(body_text[:1000])

        # 检查关键全局变量
        check = await page.evaluate("""() => ({
            hasEmconfig: !!window.emconfig,
            hasRequest: !!(window.emconfig && window.emconfig.Request),
            hasApi001: !!(window.emconfig && window.emconfig.Request && window.emconfig.Request.api001),
            hasEmDialog: !!window.emDialog,
            hasEmRuntime: !!window.emRuntime,
            inApp: window.emRuntime && window.emRuntime.InApp,
            hasEmh5: !!window.emh5,
            hasEMRead: !!window.EMRead,
        })""")
        print("\n===== 全局变量检查 =====")
        for k, v in check.items():
            print("  %s: %s" % (k, v))

        # 检查api001是否被保护
        api001_src = await page.evaluate("""() => {
            var fn = window.emconfig && window.emconfig.Request && window.emconfig.Request.api001;
            return fn ? fn.toString().slice(0, 100) : 'N/A';
        }""")
        print("\n  api001来源: %s" % api001_src)
        print("  是否被保护: %s" % ("fetch" in api001_src or "SHIPAN" in api001_src))

        # 手动调用api001获取数据
        print("\n===== 手动调用 api001 =====")
        test_types = [
            ("rt_get_rank", {"rankType": "10004", "recIdx": "0", "recCnt": "3", "rankid": "0", "appVer": "9001000"}),
            ("rt_get_info", {"zh": ZH_ID, "appVer": "9001000"}),
            ("rt_get_position", {"zh": ZH_ID, "appVer": "9001000"}),
            ("rt_get_change", {"zh": ZH_ID, "appVer": "9001000"}),
        ]

        for api_type, extra_data in test_types:
            data = {"type": api_type, **extra_data}
            result = await asyncio.wait_for(page.evaluate("""(data) => new Promise((resolve) => {
                if (!window.emconfig || !window.emconfig.Request || !window.emconfig.Request.api001) {
                    resolve({error: "api001 not available"});
                    return;
                }
                window.emconfig.Request.api001({
                    url: "rtV1",
                    type: data.type,
                    data: data,
                    success: function(t) {
                        try {
                            var d = JSON.parse(t);
                            resolve({result: d.result, msg: d.message, len: t.length, preview: t.slice(0, 200)});
                        } catch(e) { resolve({raw: t.slice(0, 200)}); }
                    },
                    error: function(e) { resolve({error: String(e)}); }
                });
                setTimeout(() => resolve({timeout: true}), 10000);
            })""", data), timeout=15)
            status = "OK" if result.get("result") == "0" else "FAIL"
            print("  [%s] %s: %s" % (status, api_type, result))

        # 打印stealth日志
        stealth_logs = [l for l in logs if "stealth" in l.lower()]
        if stealth_logs:
            print("\n===== Stealth日志 =====")
            for l in stealth_logs[:10]:
                print("  %s" % l)

        # 截图
        screenshot_path = r"D:\project\jiarenmens\data\debug\app_stealth_%s.png" % ZH_ID
        await page.screenshot(path=screenshot_path, full_page=True)
        print("\n截图: %s" % screenshot_path)

        await browser.close()

    print("\n" + "=" * 60)
    print("完成")
    print("=" * 60)


asyncio.run(main())
