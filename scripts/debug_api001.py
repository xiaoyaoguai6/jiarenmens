# -*- coding: utf-8 -*-
"""调试 api001 函数的实际执行"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
ZH_ID = "900113132"
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
        await ctx.add_init_script(STEALTH)
        page = await ctx.new_page()

        console_msgs = []
        page.on("console", lambda m: console_msgs.append("[%s] %s" % (m.type, m.text[:300])))

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(3)

        # 1. 检查 api001 函数的来源
        print("=== api001 source check ===")
        check = await page.evaluate("""() => {
            var api001 = window.emconfig && window.emconfig.Request && window.emconfig.Request.api001;
            return {
                hasApi001: !!api001,
                api001Str: api001 ? api001.toString().slice(0, 500) : 'N/A',
                hasEmconfig: !!window.emconfig,
                requestKeys: window.emconfig && window.emconfig.Request ? Object.keys(window.emconfig.Request) : [],
            };
        }""")
        for k, v in check.items():
            print("  %s: %s" % (k, v))

        # 2. 直接在页面中调用 api001 并捕获日志
        console_msgs.clear()
        print("\n=== Calling api001 with logging ===")
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            console.log("[test] Starting api001 call...");
            try {
                var opts = {
                    url: "rtV1",
                    type: "rt_get_info",
                    data: {zh: "900113132", appVer: "9001000"},
                    success: function(t) {
                        console.log("[test] api001 success, len=" + t.length);
                        resolve({ok: true, len: t.length, preview: t.slice(0, 200)});
                    },
                    error: function(e) {
                        console.log("[test] api001 error: " + e);
                        resolve({error: String(e)});
                    }
                };
                console.log("[test] Calling emconfig.Request.api001...");
                window.emconfig.Request.api001(opts);
                console.log("[test] api001 called (sync returned)");
            } catch(e) {
                console.log("[test] Exception: " + e.message);
                resolve({exception: e.message});
            }
            setTimeout(() => {
                console.log("[test] Timeout!");
                resolve({timeout: true});
            }, 8000);
        })"""), timeout=12)

        print("  Result: %s" % result)
        print("\n  Console during call:")
        for m in console_msgs:
            print("    %s" % m)

        # 3. 直接用 fetch 测试同样的 URL
        print("\n=== Direct fetch test ===")
        fetch_result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            var url = "https://emdcspzhapi.dfcfs.cn/rtV1?type=rt_get_info&zh=900113132&appVer=9001000";
            console.log("[fetch] Calling: " + url);
            fetch(url)
                .then(r => {
                    console.log("[fetch] Got response: " + r.status);
                    return r.text();
                })
                .then(t => {
                    console.log("[fetch] Body len: " + t.length);
                    resolve({ok: true, status: 200, len: t.length, preview: t.slice(0, 200)});
                })
                .catch(e => {
                    console.log("[fetch] Error: " + e.message);
                    resolve({fetchError: e.message});
                });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("  Result: %s" % fetch_result)

        await browser.close()

asyncio.run(main())
