# -*- coding: utf-8 -*-
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
with open('data/debug/pc_js_combined.js', 'r', encoding='utf-8', errors='replace') as f:
    js = f.read()

# Find ALL EMTrans calls
emtrans = re.findall(r'EMTrans\([^)]+\)', js)
print('=== EMTrans calls (%d) ===' % len(emtrans))
for e in emtrans:
    print('  %s' % e[:200])

# Find ALL path: patterns
paths = re.findall(r'path:\s*"([^"]+)"', js)
paths += re.findall(r"path:\s*'([^']+)'", js)
print('\n=== path: patterns (%d) ===' % len(set(paths)))
for p in sorted(set(paths)):
    print('  %s' % p)

# Find tripleDES context
idx = js.find('tripleDES')
if idx > -1:
    print('\n=== tripleDES context ===')
    print(js[max(0,idx-300):idx+500].replace('\n', ' ')[:800])

# Find all cfhUid references
for m in re.finditer(r'cfhUid', js):
    print('\n=== cfhUid context ===')
    print(js[max(0,m.start()-100):m.start()+200].replace('\n', ' ')[:300])
    break
