import asyncio, json, re
from pathlib import Path
from playwright.async_api import async_playwright

USER_AGENT = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) '
    'Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)'
)

CUSTOM_INFO_JS = r'''
(async function() {
    console.log('[inject-v2] Custom info loader running');

    function waitForEmconfig() {
        return new Promise(function(resolve) {
            var checks = 0;
            function check() {
                if (window.emconfig && window.emconfig.Request && window.emconfig.Request.api001) {
                    console.log('[inject-v2] emconfig ready');
                    resolve();
                } else if (checks < 50) {
                    checks++;
                    setTimeout(check, 200);
                } else {
                    console.log('[inject-v2] emconfig never loaded');
                    resolve();
                }
            }
            check();
        });
    }

    await waitForEmconfig();

    var zh = (location.search.match(/zh=([\d]+)/) || [])[1] || '900113132';
    console.log('[inject-v2] loading data for zh=' + zh);

    var types = [
        'rt_get_info',
        'rt_get_position',
        'rt_get_change',
        'rt_get_rank_detail',
        'rt_zhuhe_yk_new',
        'rt_get_zjzh',
        'rt_get_zjzh_detail',
        'rt_get_userinfo',
    ];

    var results = {};
    var done = 0;

    types.forEach(function(t) {
        window.emconfig.Request.api001({
            url: 'rtV1',
            type: 'get',
            data: {
                type: t,
                zh: zh,
                zjzh: zh,
                appVer: '9001000',
                userid: '3043345941133016',
            },
            success: function(data) {
                results[t] = { ok: true, data: String(data).slice(0, 800) };
            },
            error: function(err) {
                results[t] = { ok: false, err: String(err).slice(0, 500) };
            },
            complete: function() {
                done++;
                if (done === types.length) render();
            }
        });
    });

    setTimeout(function() {
        if (done < types.length) {
            done = types.length;
            render();
        }
    }, 15000);

    function render() {
        var el = document.getElementById('detail-content');
        if (el) {
            el.innerHTML = '<pre style=padding:10px;font-size:11px;white-space:pre-wrap>' +
                JSON.stringify(results, null, 2).replace(/</g, '&lt;') +
                '</pre>';
        }
        console.log('[inject-v2] render done, ' + Object.keys(results).length + ' results');
    }
})();
'''

async def api_request_handler(route):
    import aiohttp
    request = route.request
    url = str(request.url)
    method = request.method
    headers = dict(request.headers)
    for h in list(headers.keys()):
        if h.lower().startswith(('sec-', 'origin', 'referer')):
            del headers[h]
    headers['User-Agent'] = USER_AGENT
    headers['Referer'] = 'https://groupwap.eastmoney.com/'
    post_data = request.post_data

    try:
        async with aiohttp.ClientSession() as session:
            if method == 'GET':
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    body = await resp.read()
                    await route.fulfill(
                        status=resp.status,
                        headers={
                            'Content-Type': resp.headers.get('Content-Type', 'application/json'),
                            'Access-Control-Allow-Origin': '*',
                        },
                        body=body,
                    )
            else:
                async with session.post(url, headers=headers, data=post_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    body = await resp.read()
                    await route.fulfill(
                        status=resp.status,
                        headers={
                            'Content-Type': resp.headers.get('Content-Type', 'application/json'),
                            'Access-Control-Allow-Origin': '*',
                        },
                        body=body,
                    )
    except Exception as e:
        print(f'[route-handler] error: {e}')
        await route.fulfill(
            status=502,
            body=json.dumps({'error': str(e)}).encode(),
            headers={'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        )

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={'width': 414, 'height': 896},
            user_agent=USER_AGENT,
            locale='zh-CN', timezone_id='Asia/Shanghai',
            has_touch=True, is_mobile=True,
            device_scale_factor=3,
        )

        stealth = Path(r'D:\project\jiarenmens\src\utils\_stealth_script.js').read_text(encoding='utf-8')
        await ctx.add_init_script(stealth)

        page = await ctx.new_page()

        logs = []
        page.on('console', lambda m: logs.append(f'[{m.type}] {m.text[:300]}'))
        page.on('pageerror', lambda e: logs.append(f'[PAGE_ERR] {str(e)[:300]}'))

        await page.route('**/emdcspzhapi.dfcfs.cn/**', api_request_handler)

        async def handle_js_route(route):
            url = route.request.url
            if 'reality/info/info' in url or 'reality_info_info' in url:
                print('[route] Intercepted info JS, injecting custom loader')
                await route.fulfill(status=200, content_type='application/javascript', body=CUSTOM_INFO_JS)
            elif 'reality/detail/detail' in url or 'reality_detail_detail' in url:
                print('[route] Intercepted detail JS, injecting custom loader')
                await route.fulfill(status=200, content_type='application/javascript', body=CUSTOM_INFO_JS)
            else:
                await route.continue_()

        await page.route('**/*', handle_js_route)

        zh = '900113132'
        print(f'\n=== Loading info page for zh={zh} ===')
        await page.goto(
            f'https://groupwap.eastmoney.com/group/reality/info.html?zh={zh}',
            wait_until='domcontentloaded',
            timeout=30000
        )

        await asyncio.sleep(12)

        body = await page.evaluate('document.body ? document.body.innerHTML : "NO BODY"')
        print(f'Body length: {len(body)}')

        detail_html = await page.evaluate(
            'document.getElementById("detail-content") ? document.getElementById("detail-content").innerHTML : "NO DETAIL"'
        )
        print(f'detail-content: {detail_html[:1500]}')

        relevant = [l for l in logs if any(k in l for k in ['inject', 'stealth', 'api001', 'api003', 'PAGE_ERR', 'detail', 'error'])]
        print(f'\n--- Relevant logs ({len(relevant)}/{len(logs)}) ---')
        for l in relevant[:20]:
            print(l)

        await browser.close()

asyncio.run(main())
