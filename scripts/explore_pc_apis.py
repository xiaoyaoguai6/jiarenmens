"""
Explore PC version APIs found via Playwright intercept.
1. Analyze PC JS bundles for API patterns
2. Directly call discovered API endpoints
3. Deep-intercept to find position list API
"""
import asyncio
import json
import re
import requests
from playwright.async_api import async_playwright

ZH_ID = '900013608'
UID = '2012094520785316'
UA_PC = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


def safe_print(text):
    try:
        print(text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
    except:
        print('<encode error>')


def step1_direct_api_calls():
    """Step 1: Call discovered APIs directly."""
    print('=' * 70)
    print('STEP 1: Direct API calls to discovered endpoints')
    print('=' * 70)
    s = requests.Session()
    s.headers.update({'User-Agent': UA_PC, 'Referer': 'https://emcreative.eastmoney.com/'})

    # API 1: post_header_yield_handler
    print('\n--- API 1: spzhapi.dfcfs.cn post_header_yield_handler ---')
    for combo_id in [ZH_ID, '900304915']:
        for method in ['GET', 'POST']:
            for params in [
                {'combinationId': combo_id},
                {'combinationId': combo_id, 'type': 'position'},
                {'combinationId': combo_id, 'fieldType': 'position'},
            ]:
                try:
                    url = 'https://spzhapi.dfcfs.cn/rspThird/community/post_header_yield_handler'
                    if method == 'GET':
                        resp = s.get(url, params=params, timeout=10)
                    else:
                        resp = s.post(url, json=params, timeout=10)
                    d = resp.json()
                    safe_print('  %s %s => %s' % (method, str(params), json.dumps(d, ensure_ascii=False)[:300]))
                except Exception as e:
                    pass

    # API 2: emstockdiag
    print('\n--- API 2: emstockdiag.eastmoney.com ---')
    for path in [
        '/apistock/Tran/GetData',
        '/apistock/Tran/GetPosition',
        '/apistock/Tran/GetHold',
        '/apistock/Tran/GetStock',
        '/apistock/Tran/GetDetail',
    ]:
        for params in [
            {'zh': ZH_ID, 'uid': UID},
            {'combinationId': ZH_ID},
            {'combinationId': ZH_ID, 'uid': UID},
        ]:
            try:
                url = 'https://emstockdiag.eastmoney.com' + path
                resp = s.get(url, params=params, timeout=10)
                if resp.status_code == 200 and len(resp.text) > 30:
                    safe_print('  GET %s %s => %d %s' % (path, str(params), resp.status_code, resp.text[:300]))
            except:
                pass

    # API 3: FortuneApi
    print('\n--- API 3: emcreative FortuneApi ---')
    for path in [
        '/FortuneApi/GuBaApi/common',
        '/FortuneApi/GuBaApi/position',
        '/FortuneApi/GuBaApi/GetPosition',
        '/FortuneApi/GuBaApi/holdings',
        '/FortuneApi/GuBaApi/stockList',
        '/FortuneApi/GuBaApi/detail',
        '/FortuneApi/ShipanApi/position',
        '/FortuneApi/ShipanApi/GetPosition',
        '/FortuneApi/ShipanApi/stock',
        '/FortuneApi/ShipanApi/detail',
        '/FortuneApi/ShipanApi/info',
    ]:
        try:
            url = 'https://emcreative.eastmoney.com' + path
            resp = s.get(url, params={'uid': UID, 'zh': ZH_ID}, timeout=10)
            if resp.status_code == 200 and len(resp.text) > 30:
                safe_print('  %s => %d %s' % (path, resp.status_code, resp.text[:300]))
        except:
            pass

    # API 4: spzhapi other paths
    print('\n--- API 4: spzhapi.dfcfs.cn other paths ---')
    for path in [
        '/rspThird/community/post_header_yield_handler',
        '/rspThird/community/position_handler',
        '/rspThird/community/stock_handler',
        '/rspThird/community/detail_handler',
        '/rspThird/community/hold_handler',
        '/rspThird/shipan/position_handler',
        '/rspThird/shipan/stock_handler',
        '/rspThird/shipan/detail_handler',
        '/rspThird/api/position',
        '/rspThird/api/stock',
        '/rspThird/api/detail',
    ]:
        for params in [
            {'combinationId': ZH_ID},
            {'combinationId': ZH_ID, 'uid': UID},
            {'zh': ZH_ID},
        ]:
            try:
                url = 'https://spzhapi.dfcfs.cn' + path
                resp = s.get(url, params=params, timeout=10)
                if resp.status_code == 200 and len(resp.text) > 30:
                    safe_print('  %s %s => %d %s' % (path, str(params)[:50], resp.status_code, resp.text[:300]))
            except:
                pass


async def step2_deep_intercept():
    """Step 2: Deep intercept with Playwright - capture ALL requests including XHR."""
    print('\n' + '=' * 70)
    print('STEP 2: Deep Playwright intercept - all XHR/fetch')
    print('=' * 70)

    all_reqs = []
    all_resps = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA_PC,
            viewport={'width': 1920, 'height': 1080},
        )
        page = await ctx.new_page()

        async def on_req(req):
            all_reqs.append({
                'url': req.url,
                'method': req.method,
                'post': req.post_data,
                'headers': dict(req.headers) if req.headers else {},
            })

        async def on_resp(resp):
            try:
                ct = resp.headers.get('content-type', '')
                body = await resp.text()
                all_resps.append({
                    'url': resp.url,
                    'status': resp.status,
                    'ct': ct,
                    'body': body[:10000],
                })
            except:
                pass

        page.on('request', on_req)
        page.on('response', on_resp)

        # Load page
        url = 'https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s&anchor=3' % UID
        safe_print('Loading: %s' % url)
        await page.goto(url, timeout=30000, wait_until='networkidle')
        await asyncio.sleep(5)

        # Click on different tabs to trigger more API calls
        try:
            tabs = await page.query_selector_all('.tab-item, [data-tab], .nav-item, .tab-nav span')
            safe_print('Found %d tab elements' % len(tabs))
            for tab in tabs:
                try:
                    text = await tab.inner_text()
                    safe_print('  Tab: %s' % text.strip())
                    await tab.click()
                    await asyncio.sleep(3)
                except:
                    pass
        except Exception as e:
            safe_print('Tab click error: %s' % e)

        # Scroll
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(3)

        await ctx.close()
        await browser.close()

    # Analyze captured data
    safe_print('\n--- API-like responses ---')
    api_keywords = ['position', 'stock', 'trade', 'hold', 'detail', 'zuhe', 'combo', 'shipan', 'data', 'api']
    for r in all_resps:
        if r['status'] == 200 and r['ct'] and ('json' in r['ct'] or 'javascript' in r['ct']):
            if any(k in r['url'].lower() for k in api_keywords) or len(r['body']) < 2000:
                safe_print('\n  URL: %s' % r['url'][:150])
                safe_print('  CT: %s  Status: %d' % (r['ct'], r['status']))
                safe_print('  Body: %s' % r['body'][:500])

    # Also search all request URLs for API patterns
    safe_print('\n--- All unique request domains ---')
    domains = set()
    for r in all_reqs:
        match = re.match(r'https?://([^/]+)', r['url'])
        if match:
            domains.add(match.group(1))
    for d in sorted(domains):
        safe_print('  %s' % d)

    # Search for POST requests (often contain API data)
    safe_print('\n--- POST requests ---')
    for r in all_reqs:
        if r['method'] == 'POST':
            safe_print('  %s' % r['url'][:150])
            if r.get('post'):
                safe_print('    POST data: %s' % r['post'][:300])


async def step3_analyze_pc_js():
    """Step 3: Download and analyze PC version JS for API patterns."""
    print('\n' + '=' * 70)
    print('STEP 3: Analyze PC JS bundles for API URLs')
    print('=' * 70)

    js_urls = [
        'https://emcreative.eastmoney.com/app_fortune/person/static/script/common.js?v=1775118396324',
        'https://emcreative.eastmoney.com/app_fortune/person/static/script/index.js?v=1775118396324',
        'https://emcreative.eastmoney.com/app_fortune/person/static/script/1.js?v=1775118396324',
        'https://emcreative.eastmoney.com/app_fortune/person/static/script/6.js?v=1775118396324',
        'https://emcreative.eastmoney.com/app_fortune/person/static/script/17.js?v=1775118396324',
        'https://emcreative.eastmoney.com/app_fortune/person/static/script/18.js?v=1775118396324',
        'https://emcreative.eastmoney.com/app_fortune/person/static/script/22.js?v=1775118396324',
    ]

    s = requests.Session()
    s.headers.update({'User-Agent': UA_PC})

    all_js = ''
    for url in js_urls:
        try:
            resp = s.get(url, timeout=15)
            all_js += resp.text
            safe_print('  Downloaded %s: %d chars' % (url.split('/')[-1].split('?')[0], len(resp.text)))
        except Exception as e:
            safe_print('  Failed: %s: %s' % (url, e))

    safe_print('  Total JS: %d chars' % len(all_js))

    # Search for API URL patterns
    print('\n--- API URL patterns in JS ---')
    api_patterns = re.findall(r'["\']https?://[^"\']*(?:api|position|stock|trade|hold|detail|zuhe|shipan|data|handler)[^"\']*["\']', all_js, re.IGNORECASE)
    seen = set()
    for p in api_patterns:
        p_clean = p.strip('\'"')
        if p_clean not in seen:
            seen.add(p_clean)
            safe_print('  %s' % p_clean)

    # Search for API path patterns (relative)
    print('\n--- Relative API paths in JS ---')
    rel_patterns = re.findall(r'["\']/(?:api|rspThird|FortuneApi|apistock|shipan)[^"\']*["\']', all_js, re.IGNORECASE)
    seen2 = set()
    for p in rel_patterns:
        p_clean = p.strip('\'"')
        if p_clean not in seen2:
            seen2.add(p_clean)
            safe_print('  %s' % p_clean)

    # Search for handler/function names related to position
    print('\n--- Position-related function/variable names ---')
    pos_patterns = re.findall(r'(?:position|stock|hold|trade|detail|shipan)\w*', all_js, re.IGNORECASE)
    seen3 = set(pos_patterns)
    for p in sorted(seen3):
        if len(p) > 4:
            safe_print('  %s' % p)

    # Search for domain patterns
    print('\n--- Domain patterns ---')
    domains = re.findall(r'["\']https?://([a-zA-Z0-9._-]+\.(?:cn|com))[^"\']*["\']', all_js)
    seen4 = set(domains)
    for d in sorted(seen4):
        safe_print('  %s' % d)

    # Save full JS for offline analysis
    with open(r'D:\project\jiarenmens\data\debug\pc_js_combined.js', 'w', encoding='utf-8', errors='replace') as f:
        f.write(all_js)
    safe_print('\n  Saved combined JS to data/debug/pc_js_combined.js')


if __name__ == '__main__':
    step1_direct_api_calls()
    asyncio.run(step3_analyze_pc_js())
    asyncio.run(step2_deep_intercept())
