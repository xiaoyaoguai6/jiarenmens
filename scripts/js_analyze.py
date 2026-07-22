import re
with open("scripts/js_dump/common_1776934691271.js", "r", encoding="utf-8") as f:
    js = f.read()

types = set(re.findall(r'"(rt_\w+)"', js))
print("API types found:", types)

fields = set(re.findall(r'"(zjzh|zh|userid|user_id|uid|rankid|rankType|recIdx|recCnt)"', js))
print("Data fields:", fields)

# Extract more context around data construction for api001
for m in re.finditer(r'data:\s*\{[^}]+\}', js):
    s = m.group()
    if any(t in s for t in ['zh','zjzh','user']):
        print("data block:", s[:200])
