# -*- coding: utf-8 -*-
"""检查 api001 的 fetch 请求是否发出及响应"""
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

        # 捕获所有请求和响应
        reqs = []
        resps = []
        page.on("request", lambda r: reqs.append({"url": r.url, "method": r.method}))
        page.on("response", lambda r: resps.append({"url": r.url, "status": r.status}))

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(3)

        # 清空之前的请求记录
        reqs.clear()
        resps.clear()

        # 手动调用 api001 并同时监听网络
        print("=== Calling api001 ===")
        try:
            result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
                try {
                    window.emconfig.Request.api001({
                        url: "rtV1",
                        type: "rt_get_info",
                        data: {zh: "900113132", appVer: "9001000"},
                        success: function(t) { resolve({ok: true, len: t.length, preview: t.slice(0, 300)}); },
                        error: function(e) { resolve({error: String(e)}); }
                    });
                } catch(e) {
                    resolve({jsError: e.message});
                }
                setTimeout(() => resolve({timeout: true}), 8000);
            })"""), timeout=12)
            print("  JS result: %s" % result)
        except Exception as e:
            print("  Evaluate error: %s" % e)

        # 打印 api001 调用期间的网络请求
        print("\n=== Network during api001 (%d reqs, %d resps) ===" % (len(reqs), len(resps)))
        for r in reqs:
            if "emdcspzhapi" in r["url"] or "rtV1" in r["url"] or "apistock" in r["url"]:
                print("  REQ: %s %s" % (r["method"], r["url"][:150]))
        for r in resps:
            if "emdcspzhapi" in r["url"] or "rtV1" in r["url"] or "apistock" in r["url"]:
                print("  RESP: [%d] %s" % (r["status"], r["url"][:150]))

        # 如果没有捕获到请求，检查 fetch 是否被阻止
        if not any("emdcspzhapi" in r["url"] for r in reqs):
            print("\n=== No requests to emdcspzhapi detected! ===")
            # 直接在页面中测试 fetch
            fetch_test = await page.evaluate("""() => new Promise((resolve) => {
                fetch("https://emdcspzhapi.dfcfs.cn/rtV1?type=rt_get_rank&rankType=10004&recIdx=0&recCnt=1&rankid=0&appVer=9001000")
                    .then(r => r.text().then(t => resolve({ok: true, status: r.status, len: t.length, preview: t.slice(0, 200)})))
                    .catch(e => resolve({fetchError: e.message}));
                setTimeout(() => resolve({timeout: true}), 8000);
            })""")
            print("  Direct fetch test: %s" % fetch_test)

        await browser.close()

asyncio.run(main())
