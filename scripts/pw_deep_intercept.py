import asyncio
import json
import sys
from playwright.async_api import async_playwright

ZH_ID = '900013608'
UID = '2012094520785316'

async def main():
    all_captured = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        page = await ctx.new_page()

        async def on_resp(response):
            url = response.url
            try:
                ct = response.headers.get('content-type', '')
                if 'json' in ct or 'javascript' in ct or 'text' in ct:
                    body = await response.text()
                    if len(body) > 20:
                        all_captured.append({
                            'url': url,
                            'status': response.status,
                            'ct': ct,
                            'body': body[:5000],
                        })
            except:
                pass

        page.on('response', on_resp)

        # Load PC page with anchor=3 (positions tab)
        url = 'https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s&anchor=3' % UID
        print('Loading: %s' % url)
        await page.goto(url, timeout=30000, wait_until='networkidle')
        await asyncio.sleep(5)

        # Scroll to trigger lazy loading
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(3)

        await ctx.close()
        await browser.close()

    # Print all captured responses
    print('\n=== ALL CAPTURED RESPONSES (%d) ===' % len(all_captured))
    for i, r in enumerate(all_captured):
        print('\n[%d] %s' % (i, r['url'][:150]))
        print('    CT: %s  Status: %d  Len: %d' % (r['ct'], r['status'], len(r['body'])))
        # Print body, trying to handle encoding
        body = r['body']
        try:
            safe = body.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            print('    BODY: %s' % safe[:500])
        except:
            print('    BODY: <binary or encoding error>')

asyncio.run(main())
