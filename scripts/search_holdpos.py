# -*- coding: utf-8 -*-
import sys, io, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

for fname in ['scripts/js_dump/common_1776934691271.js', 'scripts/js_dump/vendor_1776934691271.js', 'scripts/js_dump/reality_info_info_1776934691271.js']:
    if not os.path.exists(fname):
        continue
    with open(fname, 'r', encoding='utf-8', errors='replace') as f:
        js = f.read()
    for kw in ['holdPos', 'webYkRate', 'BlockName', 'blkRatio', '__zxjg', 'cbj', '__code', '__name']:
        idx = js.find(kw)
        if idx > -1:
            print('\n=== %s in %s ===' % (kw, fname.split('/')[-1]))
            print(js[max(0,idx-200):idx+200].replace('\n', ' ')[:400])
