import asyncio
import json
from playwright.async_api import async_playwright

ZH_ID = '900013608'
UID = '2012094520785316'
STEALTH_JS = """
window.emh5 = {
    ready: function() {},
    on: function() {},
    emit: function() {},
    bridge: {
        call: function(name, data, cb) { if (cb) cb({}); },
        on: function() {},
    },
    getSystemInfo: function(cb) { if (cb) cb({platform: 'iphone', model: 'iPhone'}); },
};
window.emRuntime = { platform: 'iphone', version: '12.0.0' };
window.EMProjJs = { version: '12.0.0' };
window.EMRead = { version: '12.0.0' };
window.emconfig = {
    Request: {
        api001: function(opts) {
            console.log('emconfig.Request.api001 called:', JSON.stringify(opts));
            return Promise.resolve({result: '-1'});
        },
        api003: function(opts) {
            console.log('emconfig.Request.api003 called:', JSON.stringify(opts));
            return Promise.resolve({result: '-1'});
        },
    },
};
window.shipan = function() {};
window.moni = function() {};
window.guba = function() {};
"""

async def main():
    captured = []
    responses_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # --- PC version ---
        print('=== TEST: emcreative.eastmoney.com PC version ===')
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        page = await ctx.new_page()

        async def on_req(request):
            url = request.url
            if any(k in url.lower() for k in ['api', 'position', 'stock', 'trade', 'info', 'detail', 'zuhe', 'combo', 'hold', 'rtv1', 'srtv1', 'push2', 'datacenter', 'ztbg']):
                captured.append({'url': url, 'method': request.method, 'post': request.post_data})

        async def on_resp(response):
            url = response.url
            if any(k in url.lower() for k in ['api', 'position', 'stock', 'trade', 'detail', 'zuhe', 'combo', 'hold', 'rtv1', 'srtv1', 'push2', 'datacenter']):
                try:
                    body = await response.text()
                    print('[RESP] %d %s' % (response.status, url[:120]))
                    if 10 < len(body) < 5000:
                        print('  BODY: %s' % body[:500])
                    responses_data.append({'url': url, 'status': response.status, 'body': body[:2000]})
                except:
                    pass

        page.on('request', on_req)
        page.on('response', on_resp)

        url = 'https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s&anchor=3' % UID
        print('Loading: %s' % url)
        try:
            await page.goto(url, timeout=30000, wait_until='networkidle')
        except Exception as e:
            print('Load error: %s' % e)

        await asyncio.sleep(5)
        text = await page.inner_text('body')
        print('Body text: %s' % text[:600])
        await ctx.close()

        # --- Mobile H5 version with stealth ---
        print()
        print('=== TEST: groupwap mobile H5 with stealth ===')
        ctx2 = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)',
            viewport={'width': 414, 'height': 896},
            device_scale_factor=3,
        )
        await ctx2.add_init_script(STEALTH_JS)
        page2 = await ctx2.new_page()
        page2.on('request', on_req)
        page2.on('response', on_resp)

        url2 = 'https://groupwap.eastmoney.com/group/reality/info.html?zh=%s' % ZH_ID
        print('Loading: %s' % url2)
        try:
            await page2.goto(url2, timeout=30000, wait_until='networkidle')
        except Exception as e:
            print('Load error: %s' % e)

        await asyncio.sleep(3)
        text2 = await page2.inner_text('body')
        print('Body text: %s' % text2[:600])

        # Try detail page too
        url3 = 'https://groupwap.eastmoney.com/group/reality/detail.html?zh=%s' % ZH_ID
        print()
        print('Loading detail: %s' % url3)
        try:
            await page2.goto(url3, timeout=30000, wait_until='networkidle')
        except Exception as e:
            print('Load error: %s' % e)

        await asyncio.sleep(3)
        text3 = await page2.inner_text('body')
        print('Body text: %s' % text3[:600])

        await ctx2.close()
        await browser.close()

    print()
    print('=== Captured %d requests ===' % len(captured))
    for c in captured:
        print('  %s %s' % (c['method'], c['url'][:140]))
        if c.get('post'):
            print('    POST: %s' % c['post'][:200])

    print()
    print('=== Responses with data ===')
    for r in responses_data:
        if r['status'] == 200 and len(r['body']) > 20:
            print('  %s' % r['url'][:120])
            print('  %s' % r['body'][:300])

asyncio.run(main())
