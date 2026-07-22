"""
Scrape position data from the PC version of EastMoney Shipan.

Strategy:
1. Load the PC page with Playwright (using existing chromium-1148)
2. Intercept ALL network requests to discover the position list API
3. Also scrape the rendered DOM as a fallback
4. Output results as JSON
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright

ZH_ID = '900013608'
UID = '2012094520785316'
UA_PC = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)
CHROMIUM_PATH = (
    r'C:\Users\lwz18\AppData\Local\ms-playwright'
    r'\chromium-1148\chrome-win\chrome.exe'
)


def safe(text):
    return text.encode('utf-8', errors='replace').decode(
        'utf-8', errors='replace'
    )


async def intercept_and_scrape(zh_id, uid):
    """Load PC page, intercept all network calls, scrape DOM."""
    all_requests = []
    all_responses = []
    json_responses = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
        )
        ctx = await browser.new_context(
            user_agent=UA_PC,
            viewport={'width': 1920, 'height': 1080},
        )
        page = await ctx.new_page()

        async def on_request(req):
            all_requests.append({
                'url': req.url,
                'method': req.method,
                'post_data': req.post_data,
            })

        async def on_response(resp):
            try:
                ct = resp.headers.get('content-type', '')
                status = resp.status
                if status == 200 and (
                    'json' in ct
                    or 'javascript' in ct
                    or 'text/plain' in ct
                ):
                    body = await resp.text()
                    entry = {
                        'url': resp.url,
                        'status': status,
                        'content_type': ct,
                        'body': body,
                    }
                    all_responses.append(entry)
                    if 'json' in ct:
                        json_responses.append(entry)
            except Exception:
                pass

        page.on('request', on_request)
        page.on('response', on_response)

        # Load PC page
        url = (
            f'https://emcreative.eastmoney.com/app_fortune/'
            f'person/index.html?uid={uid}&anchor=3'
        )
        print(safe(f'[1] Loading: {url}'))
        try:
            await page.goto(
                url, timeout=30000, wait_until='domcontentloaded'
            )
            await asyncio.sleep(8)
        except Exception as e:
            print(safe(f'  Page load error: {e}'))

        # Click tabs to trigger data loads
        print('[2] Clicking tabs...')
        tab_sels = [
            '.tab-item', '[data-tab]', '.nav-item',
            '.tab-nav span', '.tab-nav a',
            'li.tab', 'div.tab', 'span.tab',
        ]
        clicked = 0
        for sel in tab_sels:
            try:
                tabs = await page.query_selector_all(sel)
                for tab in tabs:
                    text = (await tab.inner_text()).strip()
                    if text:
                        print(safe(f'  Tab: {text}'))
                        await tab.click()
                        await asyncio.sleep(3)
                        clicked += 1
            except Exception:
                pass
        print(f'  Clicked {clicked} tabs')

        # Scroll to trigger lazy loading
        print('[3] Scrolling...')
        for _ in range(5):
            await page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(1)

        # Extract page content
        print('[4] Extracting content...')
        page_text = await page.evaluate('document.body.innerText')

        # DOM stock extraction
        print('[5] DOM stock extraction...')
        dom_stocks = await page.evaluate('''() => {
            const results = [];
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                const text = el.innerText || '';
                const m = text.match(/\\b[036]\\d{5}\\b/g);
                if (m && m.length > 0) {
                    results.push({
                        tag: el.tagName,
                        cls: el.className,
                        text: text.substring(0, 500),
                        stocks: m
                    });
                }
            }
            return results.slice(0, 50);
        }''')

        # Screenshot
        await page.screenshot(
            path=r'D:\project\jiarenmens\data\debug\pc_page.png',
            full_page=True,
        )
        print('[6] Screenshot saved')

        await ctx.close()
        await browser.close()

    # Report
    print('\n' + '=' * 70)
    print('RESULTS')
    print('=' * 70)

    domains = set()
    for r in all_requests:
        m = re.match(r'https?://([^/]+)', r['url'])
        if m:
            domains.add(m.group(1))
    print('\n--- Domains ---')
    for d in sorted(domains):
        print(safe(f'  {d}'))

    print(f'\n--- JSON responses ({len(json_responses)}) ---')
    for r in json_responses:
        print(safe(f'  URL: {r["url"]}'))
        print(safe(f'  Body: {r["body"][:500]}'))
        print()

    print(f'\n--- Non-static responses ({len(all_responses)}) ---')
    for r in all_responses:
        if 'static/' not in r['url'] and 'css' not in r['content_type']:
            print(safe(
                f'  [{r["status"]}] {r["content_type"][:30]:30s} '
                f'{r["url"][:120]}'
            ))

    print(f'\n--- DOM stock data ({len(dom_stocks)} elements) ---')
    for item in dom_stocks[:20]:
        print(safe(
            f'  {item["tag"]} .{item.get("cls","")} '
            f'stocks={item.get("stocks",[])}'
        ))
        print(safe(f'    {item["text"][:200]}'))

    print(f'\n--- Page text (first 2000) ---')
    print(safe(page_text[:2000]))

    # Save full JSON
    results = {
        'zh_id': zh_id,
        'uid': uid,
        'requests': [r['url'] for r in all_requests],
        'json_responses': [
            {'url': r['url'], 'body': r['body'][:5000]}
            for r in json_responses
        ],
        'dom_stocks': dom_stocks,
        'page_text': page_text[:5000],
    }
    out = r'D:\project\jiarenmens\data\debug\pc_intercept_results.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f'\nResults saved to {out}')
    return results


if __name__ == '__main__':
    asyncio.run(intercept_and_scrape(ZH_ID, UID))
