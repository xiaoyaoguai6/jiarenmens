# -*- coding: utf-8 -*-
"""分析页面 JS 的 api001 内部实现"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
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
        # 不注入 stealth，让页面的 JS 自然加载
        page = await ctx.new_page()

        all_resps = []
        page.on("response", lambda r: all_resps.append({"url": r.url, "status": r.status}))

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(3)

        # 分析 common.js 中 emconfig 的定义
        print("=== emconfig 分析 ===")
        result = await page.evaluate("""() => {
            var ec = window.emconfig;
            if (!ec) return {error: "no emconfig"};
            var req = ec.Request;
            if (!req) return {error: "no Request"};
            return {
                requestKeys: Object.keys(req),
                api001Type: typeof req.api001,
                api001Str: req.api001 ? req.api001.toString().slice(0, 500) : 'N/A',
            };
        }""")
        for k, v in result.items():
            print("  %s: %s" % (k, v))

        # 检查 api001 引用的内部函数
        print("\n=== api001 闭包分析 ===")
        result2 = await page.evaluate("""() => {
            try {
                var fn = window.emconfig.Request.api001;
                var fnStr = fn.toString();
                // 提取函数体
                var body = fnStr.slice(fnStr.indexOf('{') + 1, fnStr.lastIndexOf('}'));
                return {
                    body: body.trim(),
                    length: fnStr.length,
                    params: fn.toString().match(/function\s*\(([^)]*)\)/)?.[1] || 'unknown',
                };
            } catch(e) { return {error: e.message}; }
        }""")
        for k, v in result2.items():
            print("  %s: %s" % (k, v))

        # 检查页面是否定义了 XMLHttpRequest 或其他请求机制
        print("\n=== 请求机制检查 ===")
        result3 = await page.evaluate("""() => {
            return {
                hasXHR: typeof XMLHttpRequest !== 'undefined',
                hasFetch: typeof fetch !== 'undefined',
                hasXDomainRequest: typeof XDomainRequest !== 'undefined',
                // 检查 emRead bridge
                hasEmRead: typeof window.EMRead !== 'undefined',
                emReadKeys: window.EMRead ? Object.getOwnPropertyNames(window.EMRead).slice(0, 20) : [],
            };
        }""")
        for k, v in result3.items():
            print("  %s: %s" % (k, v))

        # 尝试用页面自己的 api001 调用（不替换），看它到底在做什么
        print("\n=== 页面 api001 原始调用 ===")
        # 先注入一个 XMLHttpRequest 拦截器
        await page.evaluate("""() => {
            window.__xhrLog = [];
            var origOpen = XMLHttpRequest.prototype.open;
            var origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url) {
                this.__url = url;
                this.__method = method;
                return origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function(body) {
                window.__xhrLog.push({method: this.__method, url: this.__url, body: body ? body.slice(0, 200) : null});
                return origSend.apply(this, arguments);
            };
        }""")

        # 也拦截 fetch
        await page.evaluate("""() => {
            window.__fetchLog = [];
            var origFetch = window.fetch;
            window.fetch = function(url, opts) {
                window.__fetchLog.push({url: typeof url === 'string' ? url : url.url, method: opts?.method || 'GET'});
                return origFetch.apply(this, arguments);
            };
        }""")

        # 调用页面的 api001
        result4 = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.Request.api001({
                url: "rtV1",
                type: "rt_get_rank",
                data: {rankType: "10004", recIdx: "0", recCnt: "3", rankid: "0", appVer: "9001000"},
                success: function(t) { resolve({ok: true, preview: t.slice(0, 200)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("  Result: %s" % result4)

        # 检查拦截到的请求
        xhr_log = await page.evaluate("window.__xhrLog || []")
        fetch_log = await page.evaluate("window.__fetchLog || []")
        print("\n  XHR requests: %d" % len(xhr_log))
        for x in xhr_log[:5]:
            print("    %s %s" % (x.get("method"), x.get("url", "")[:100]))
        print("  Fetch requests: %d" % len(fetch_log))
        for f in fetch_log[:5]:
            print("    %s %s" % (f.get("method"), f.get("url", "")[:100]))

        await browser.close()

asyncio.run(main())
