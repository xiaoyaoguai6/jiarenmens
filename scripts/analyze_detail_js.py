"""Analyze the detail.html JS to find API call patterns."""
import re
import json

with open("D:/project/jiarenmens/scripts/js_dump/reality_detail_detail_1776934691271.js", "r", encoding="utf-8") as f:
    content = f.read()

print(f"Length: {len(content)}")

# Find all occurrences of key patterns
for pattern in ["shipan", "rt_get", "api001", "api003", "emconfig", "Request"]:
    matches = list(re.finditer(pattern, content))
    if matches:
        print(f"\n=== {pattern} ({len(matches)} matches) ===")
        for m in matches[:10]:
            s = max(0, m.start() - 80)
            e = min(len(content), m.end() + 200)
            snippet = content[s:e]
            print(f"  ...{snippet}...")
            print()
