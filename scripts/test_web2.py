import requests
import json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.eastmoney.com/',
})

urls = [
    'https://web2.eastmoney.com/zuhe/API/ZuheInfo.aspx?ZH=900013608',
    'https://web2.eastmoney.com/zuhe/API/ZuhePosition.aspx?ZH=900013608',
    'https://web2.eastmoney.com/zuhe/API/ZuheStock.aspx?ZH=900013608',
    'https://web2.eastmoney.com/zuhe/JS.aspx?type=9&ZH=900013608',
    'https://web2.eastmoney.com/zuhe/JS.aspx?type=1&ZH=900013608',
]

for url in urls:
    r = s.get(url, timeout=15)
    with open('data/debug/web2_' + url.split('/')[-1].split('?')[0] + '_' + str(hash(url) % 10000) + '.txt', 'wb') as f:
        f.write(r.content)
    text = r.content.decode('utf-8', errors='replace')
    # Write to file for safe reading
    fname = 'data/debug/web2_check_' + url.split('/')[-1].split('?')[0] + '.txt'
    with open(fname, 'w', encoding='utf-8') as f:
        f.write('URL: ' + url + '\n')
        f.write('Status: ' + str(r.status_code) + '  Content-Type: ' + r.headers.get('content-type', '') + '\n')
        f.write('Length: ' + str(len(text)) + '\n')
        f.write('First 2000 chars:\n')
        f.write(text[:2000] + '\n')
    print('Written: ' + fname)
