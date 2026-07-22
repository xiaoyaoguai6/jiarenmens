# -*- coding: utf-8 -*-
"""
关键发现：AsyncRequestTran.api001 使用 /Tran/GetData 端点（已 404）。
但 Request.api001 使用 /rtV1 端点（仍存活）。
页面的 Request.api001 不发出请求是因为它使用了内部的 n() 函数。

解决方案：修改 stealth 脚本，让 Request.api001 使用 fetch + /rtV1，
同时让页面的数据加载代码能正确调用 Request.api001。

当前问题：页面的 detail.html 的 JS 不再调用 api001 加载数据（2026-04-16 禁用）。
所以我们需要自己调用 api001 获取数据。

策略：
1. 用 stealth 脚本保护 Request.api001 为我们的 fetch 版本
2. 用 Playwright route() 代理绕过 CORS
3. 手动调用 api001 获取数据
4. 解析返回的数据
"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from playwright.async_api import async_playwright
import requests as req_lib

STEALTH = Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js").read_text(encoding="utf-8")
CHROME = r"C:\Users\lwz18\AppData\Local\ms-playwright\chromium-1148\chrome-win\chrome.exe"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"

session = req_lib.Session()
session.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

async def route_handler(route):
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
    ZH_ID = "900113132"

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
        await page.route("**/emdcspzhapi.dfcfs.cn/**", route_handler)

        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s" % ZH_ID,
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(3)

        # 用我们的 api001 (fetch + /rtV1) 获取各种数据
        tests = [
            ("rt_get_rank (baseline)", {"type": "rt_get_rank", "rankType": "10004", "recIdx": "0", "recCnt": "3", "rankid": "0", "appVer": "9001000"}),
            ("rt_get_info", {"type": "rt_get_info", "zh": ZH_ID, "appVer": "9001000"}),
            ("rt_get_position", {"type": "rt_get_position", "zh": ZH_ID, "appVer": "9001000"}),
            ("rt_get_change", {"type": "rt_get_change", "zh": ZH_ID, "appVer": "9001000"}),
            ("rt_zhuhe_yk_new", {"type": "rt_zhuhe_yk_new", "zh": ZH_ID, "recIdx": "0", "recCnt": "100", "ykType": "20", "indexCode": "000300", "appVer": "9001000"}),
        ]

        for name, data in tests:
            print("\n=== %s ===" % name)
            result = await asyncio.wait_for(page.evaluate("""(data) => new Promise((resolve) => {
                window.emconfig.Request.api001({
                    url: "rtV1",
                    type: data.type,
                    data: data,
                    success: function(t) {
                        try {
                            var d = JSON.parse(t);
                            resolve({result: d.result, msg: d.message, dataLen: t.length, preview: t.slice(0, 200)});
                        } catch(e) { resolve({raw: t.slice(0, 200)}); }
                    },
                    error: function(e) { resolve({error: String(e)}); }
                });
                setTimeout(() => resolve({timeout: true}), 8000);
            })""", data), timeout=12)
            print("  %s" % result)

        # 尝试用 PC 页面的 uid 获取更多数据
        print("\n=== 用 uid 测试 ===")
        uid_result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.Request.api001({
                url: "rtV1",
                type: "rt_zhuhe_yk_new",
                data: {zh: "900113132", uid: "5887346444580316", recIdx: "0", recCnt: "100", ykType: "20", indexCode: "000300", appVer: "9001000"},
                success: function(t) { resolve({ok: true, preview: t.slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("  %s" % uid_result)

        await browser.close()

asyncio.run(main())
