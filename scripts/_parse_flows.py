from pathlib import Path
from mitmproxy import io as mitmio
try:
    reader = mitmio.FlowReader(Path(r'D:\project\jiarenmens\data\recon\realtime_snap.flows').open('rb'))
    shown = 0
    for flow in reader.stream():
        req = flow.request
        resp = flow.response
        host = req.host or ''
        url = req.url or req.pretty_url
        if not ('eastmoney' in host or 'dfcfs' in host):
            continue
        print(f'--- {req.method} {url} ->', f'{resp.status_code}' if resp else 'NO RESP', end=' ')
        if resp:
            try: rb = resp.get_text(strict=False) or ''
            except: rb = '<bin>'
            print(f'len={len(resp.content)}')
            if 'rtV' in url or 'spzhapi' in url or 'emdc' in url.lower() or 'position' in url.lower() or 'combination' in url.lower():
                # show body in detail
                if req.body:
                    try: reqbody = req.get_text(strict=False) or ''
                    except: reqbody = '<bin>'
                    print('REQ BODY:', reqbody[:600])
                print('RESP BODY:', rb[:1500])
        shown += 1
        if shown >= 200: 
            break
    print(f'TOTAL_INSPECTED={shown}')
except Exception as e:
    print(f'ERR: {e}')
