# -*- coding: utf-8 -*-
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
with open("scripts/js_dump/common_1776934691271.js", "r", encoding="utf-8", errors="replace") as f:
    js = f.read()

types = re.findall(r"rt_[a-zA-Z_]+", js)
print("=== All rt_ types ===")
for t in sorted(set(types)):
    print("  %s" % t)

api_paths = re.findall(r"[\"\']([a-zA-Z0-9_/]+(?:handler|Handler|api|Api|Json|json|aspx|ASPX))[\"\']\s*", js)
print("\n=== API paths ===")
for p in sorted(set(api_paths)):
    print("  %s" % p)

for m in re.finditer(r"get[Dd]ata|GetData", js):
    print("\n=== getData context ===")
    print(js[max(0,m.start()-200):m.start()+200].replace("\n", " ")[:400])
