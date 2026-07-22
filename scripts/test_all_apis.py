# -*- coding: utf-8 -*-
"""测试路由拦截下各种 API 是否可用，并尝试从 H5 页面加载数据"""
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

        # 先加载页面让 emconfig 初始化
        await page.goto(
            "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(3)

        # 测试各种 API type
        types = ["rt_get_rank", "rt_get_info", "rt_get_position", "rt_get_change", "rt_zhuhe_yk_new"]
        for api_type in types:
            data_param = {"zh": "900113132", "appVer": "9001000"}
            if api_type == "rt_get_rank":
                data_param.update({"rankType": "10004", "recIdx": "0", "recCnt": "5", "rankid": "0"})
            result = await asyncio.wait_for(page.evaluate("""(data) => new Promise((resolve) => {
                window.emconfig.Request.api001({
                    url: "rtV1",
                    type: data.type,
                    data: data,
                    success: function(t) {
                        try {
                            var d = JSON.parse(t);
                            resolve({ok: true, result: d.result, preview: t.slice(0, 200)});
                        } catch(e) {
                            resolve({ok: true, raw: t.slice(0, 200)});
                        }
                    },
                    error: function(e) { resolve({error: String(e)}); }
                });
                setTimeout(() => resolve({timeout: true}), 8000);
            })""", {"type": api_type, **data_param}), timeout=12)
            print("%s: %s" % (api_type, result))

        # 尝试通过 api003 调用 zuheV64
        print("\n=== api003 zuheV64 ===")
        result = await asyncio.wait_for(page.evaluate("""() => new Promise((resolve) => {
            window.emconfig.Request.api003({
                data: {
                    path: "zuheV64/JS.aspx",
                    pageUrl: location.href,
                    urlParm: JSON.stringify({type: "rt_zhuhe_yk_new", zh: "900113132", appVer: "9001000"}),
                },
                success: function(t) { resolve({ok: true, preview: t.slice(0, 300)}); },
                error: function(e) { resolve({error: String(e)}); }
            });
            setTimeout(() => resolve({timeout: true}), 8000);
        })"""), timeout=12)
        print("api003: %s" % result)

        await browser.close()

asyncio.run(main())
