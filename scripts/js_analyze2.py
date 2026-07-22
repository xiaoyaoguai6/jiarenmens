import re

with open("scripts/js_dump/reality_info_info_1776934691271.js", "r", encoding="utf-8") as f:
    js = f.read()
types = set(re.findall(r'"(rt_\w+)"', js))
print("info.js API types:", types)
fields = set(re.findall(r'"(zjzh|zh|userid|user_id|uid|rankid|rankType|recIdx|recCnt)"', js))
print("info.js data fields:", fields)

with open("scripts/js_dump/reality_detail_detail_1776934691271.js", "r", encoding="utf-8") as f:
    js = f.read()
types = set(re.findall(r'"(rt_\w+)"', js))
print("detail.js API types:", types)
fields = set(re.findall(r'"(zjzh|zh|userid|user_id|uid|rankid|rankType|recIdx|recCnt)"', js))
print("detail.js data fields:", fields)
