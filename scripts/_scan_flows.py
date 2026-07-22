import sys
from pathlib import Path
from mitmproxy import io as mitmio
rf = Path(r'D:\project\jiarenmens\data\recon\realtime.flows')
reader = mitmio.FlowReader(rf.open('rb'))
shown = 0
for flow in reader.stream():
    req = flow.request
    resp = flow.response
    if not (req.host.endswith('eastmoney.com') or req.host.endswith('dfcfs.cn')):
        continue
    print('=====', req.method, req.url, '->', resp.status_code if resp else 'no-resp')
    # show request body
    if req.method in ('POST', 'PUT'):
        try: body = req.get_text(strict=False) or ''
        except: body = '<bin>'
        print('REQ BODY:', body[:300])
    # show response body (first 500 chars)
    if resp:
        try: rb = resp.get_text(strict=False) or ''
        except: rb = '<bin>'
        print('RESP BODY:', rb[:500])
    shown += 1
    if shown >= 40:
        break
