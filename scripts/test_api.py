import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright
from src.config import USER_AGENT

stealth = open(Path(r"D:\project\jiarenmens\src\utils\_stealth_script.js"), "r", encoding="utf-8").read()

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent=USER_AGENT,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            has_touch=True, is_mobile=True, device_scale_factor=3,
        )
        await ctx.add_init_script(stealth)
        page = await ctx.new_page()

        await page.goto("https://groupwap.eastmoney.com/group/reality/info.html?zh=900113132", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(10)

        zh = "900113132"
        types_to_try = [
            "rt_get_info", "rt_get_zjzh", "rt_get_zjzh_detail", "rt_get_userinfo",
            "rt_get_position", "rt_get_change", "rt_detail", "info", "detail",
        ]
        
        for api_type in types_to_try:
            code = """
                (function() {
                    return new Promise(function(resolve) {
                        try {
                            window.emconfig.Request.api001({
                                url: "rtV1",
                                type: "%s",
                                data: { zjzh: "%s", zh: "%s", appVer: "9001000" },
                                success: function(t) { resolve({ok: true, data: t.slice(0, 500)}); },
                                error: function(t) { resolve({ok: false, err: String(t).slice(0, 200)}); }
                            });
                        } catch(e) { resolve({ok: false, err: e.message}); }
                    });
                })()
            """ % (api_type, zh, zh)
            result = await page.evaluate(code)
            ok = result.get("ok", False)
            preview = (result.get("data") or result.get("err", ""))[:150]
            print("%s -> %s %s" % (api_type, "OK" if ok else "ERR", preview))
        
        await browser.close()

asyncio.run(test())
