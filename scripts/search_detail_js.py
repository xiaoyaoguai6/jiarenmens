# -*- coding: utf-8 -*-
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('scripts/js_dump/reality_detail_detail_1776934691271.js', 'r', encoding='utf-8', errors='replace') as f:
    js = f.read()
print('Detail JS length:', len(js))

# Find all quoted strings
strings = re.findall(r'"([^"]{3,80})"', js)
api_strings = [s for s in strings if any(k in s.lower() for k in ['api', 'url', 'handler', 'position', 'trade', 'stock', 'detail', 'change', 'zh=', 'uid=', 'http', 'json', 'getdata'])]
print('\n=== API-like strings ===')
for s in sorted(set(api_strings)):
    print('  %s' % s)

# Find all function names
funcs = re.findall(r'function\s+(\w+)', js)
print('\n=== Functions (%d) ===' % len(funcs))
for f in sorted(set(funcs)):
    print('  %s' % f)

# Find AJAX/fetch/XHR patterns
for pattern in [r'\.get\([^)]+\)', r'\.post\([^)]+\)', r'ajax\([^)]+\)', r'fetch\([^)]+\)', r'\$\.get\([^)]+\)', r'\$\.post\([^)]+\)']:
    matches = re.findall(pattern, js, re.IGNORECASE)
    if matches:
        print('\n=== %s ===' % pattern[:20])
        for m in matches[:10]:
            print('  %s' % m[:200])

# Find Vue component names
components = re.findall(r'components?\s*:\s*\{([^}]+)\}', js)
for c in components:
    print('\n=== Components ===')
    print('  %s' % c[:200])

# Also check common.js
print('\n\n=== COMMON JS ===')
with open('scripts/js_dump/common_1776934691271.js', 'r', encoding='utf-8', errors='replace') as f:
    js_common = f.read()
print('Common JS length:', len(js_common))
common_strings = re.findall(r'"([^"]{3,80})"', js_common)
api_strings2 = [s for s in common_strings if any(k in s.lower() for k in ['api', 'position', 'trade', 'stock', 'detail', 'change', 'handler', 'rtv1', 'rt_', 'shipan', 'zuhe'])]
print('\n=== API strings in common.js ===')
for s in sorted(set(api_strings2)):
    print('  %s' % s)
