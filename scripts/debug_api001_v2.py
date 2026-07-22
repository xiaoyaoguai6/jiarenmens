# -*- coding: utf-8 -*-
"""调试页面的 api001 实际实现"""
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

        reqs = []
        page.on("request", lambda r: reqs.append({"url": r.url, "method": r.method, "post": r.post_data}))

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(3)
        reqs.clear()

        # 调用 api001 并检查实际发出的请求
        print("=== Calling page's api001 ===")
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.Request.api001({
                url: "rtV1",
                type: "rt_get_info",
                data: {zh: "900113132", appVer: "9001000"},
                success: function(t) { resolve({ok: true, len: t.length, preview: t.slice(0, 200)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("  Result: %s" % result)

        print("\n=== Network requests during api001 ===")
        for r in reqs:
            print("  %s %s" % (r["method"], r["url"][:150]))
            if r["post"]:
                print("    POST: %s" % r["post"][:200])

        # 直接调用我们的 __api001（绕过页面版本）
        reqs.clear()
        print("\n=== Calling our __api001 directly ===")
        result2 = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            // 构造和页面 api001 一样的 URL
            var url = "https://emdcspzhapi.dfcfs.cn/rtV1";
            var data = {zh: "900113132", appVer: "9001000"};
            var parts = [];
            for (var k in data) parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(data[k]));
            var fullUrl = url + "?" + parts.join("&");
            console.log("[our] Fetching: " + fullUrl);
            fetch(fullUrl)
                .then(function(r) { return r.text(); })
                .then(function(t) { resolve({ok: true, len: t.length, preview: t.slice(0, 200)}); })
                .catch(function(e) { resolve({error: e.message}); });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("  Result: %s" % result2)

        print("\n=== Network requests ===")
        for r in reqs:
            print("  %s %s" % (r["method"], r["url"][:150]))

        await browser.close()

asyncio.run(main())
