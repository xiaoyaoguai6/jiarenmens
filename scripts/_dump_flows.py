"""
读 realtime_snap.flows 里的所有流,bypass tnetstring 解析失败问题:
直接 byte 模式扫 "method" 串前面/后面的字符串提取所有 method 名.
"""
import re, sys
from pathlib import Path
p = Path(r"D:\project\jiarenmens\data\recon\realtime_snap.flows")
data = p.read_bytes()
print("file size:", len(data))

# 找所有 "method":"xxx" 模式 (tnetstring 内会有 JSON)
methods = set()
for m in re.finditer(rb'"method"\s*:\s*"([a-zA-Z_][a-zA-Z0-9_]+)"', data):
    methods.add(m.group(1).decode("ascii", "replace"))
print()
print("=== distinct method names found in flows ===")
for m in sorted(methods):
    print(" ", m)

# 也找 "type":"xxx" 模式 (rtV1 GET query)
print()
print("=== distinct type values (rtV1 GET) ===")
types = set()
for m in re.finditer(rb'"type"\s*:\s*"([a-zA-Z0-9_]+)"', data):
    types.add(m.group(1).decode("ascii","replace"))
for t in sorted(types):
    print(" ", t)

# 直接 raw 扫 "?type=..." 模式
print()
print("=== url query type= values (raw url scan) ===")
qs = set()
for m in re.finditer(rb'type=([a-zA-Z0-9_]+)', data):
    qs.add(m.group(1).decode("ascii","replace"))
for q in sorted(qs):
    print(" ", q)

# 找所有 url host
print()
print("=== url hosts ===")
hosts = set()
for m in re.finditer(rb'https?://([a-z0-9.]+)/', data):
    hosts.add(m.group(1).decode("ascii","replace"))
for h in sorted(hosts):
    print(" ", h)