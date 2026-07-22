# -*- coding: utf-8 -*-
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
with open('data/debug/pc_js_combined.js', 'r', encoding='utf-8', errors='replace') as f:
    js = f.read()
print('Total JS chars:', len(js))

# Search for rspThird paths
rsp = re.findall(r'rspThird/[a-zA-Z_/]+handler', js, re.IGNORECASE)
for r in sorted(set(rsp)):
    print('rspThird:', r)

# Search for emstockdiag paths
em = re.findall(r'v\d/mobileadapter/[a-zA-Z_]+', js, re.IGNORECASE)
for e in sorted(set(em)):
    print('emstockdiag:', e)

# Search for positionlist/tradelist context
for kw in ['positionlist', 'tradelist', 'detail_handler', 'stocklist', 'info_handler', 'gszcount']:
    idx = js.find(kw)
    if idx > -1:
        snippet = js[max(0,idx-200):idx+200]
        print('\nContext for %s:' % kw)
        print(snippet.replace('\n', ' ')[:400])
