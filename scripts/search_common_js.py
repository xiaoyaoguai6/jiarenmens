# -*- coding: utf-8 -*-
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
with open('scripts/js_dump/common_1776934691271.js', 'r', encoding='utf-8', errors='replace') as f:
    js = f.read()

for m in re.finditer(r'zuheV64', js):
    print('=== zuheV64 ===')
    print(js[max(0,m.start()-300):m.start()+500].replace('\n', ' ')[:800])
    print()

for m in re.finditer(r'rt_zhuhe', js):
    print('=== rt_zhuhe ===')
    print(js[max(0,m.start()-200):m.start()+300].replace('\n', ' ')[:500])
    print()
    break

for m in re.finditer(r'push2url|rtV1url', js):
    print('=== url config ===')
    print(js[max(0,m.start()-100):m.start()+200].replace('\n', ' ')[:300])
    break

types = re.findall(r'type:\s*"([^"]+)"', js)
print('\n=== All type values ===')
for t in sorted(set(types)):
    print('  %s' % t)
