import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml

adb = Adb()
print('focus now:', adb.current_focus())

# Truncate positions.jsonl
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

# tap bottom 自 (right edge before 行情 text)
# The 5 bottom tabs: 首页 (57-123), 社区 (237-303), 自 (417-483), 行情 (597-663), 理财 (777-843), 交易 (957-1023)
# Their bounds are at y=1857-1901
adb.tap(450, 1879)  # 自
time.sleep(3)
print('focus:', adb.current_focus())

# Dump UI again
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_after_self_tab.xml')
nodes = parse_ui_xml(xml)
print('== text nodes after 自 tap ==')
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown > 30: break

# tap '实盘榜单' header tab if present
ok = tap_text_if_present(adb, '实盘榜单')
print('tap 实盘榜单 ->', ok)
time.sleep(1)
ok = tap_text_if_present(adb, '实盘')
print('tap 实盘 ->', ok)
time.sleep(2)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_after_shipan_tab_v3.xml')
nodes = parse_ui_xml(xml)
print('== text nodes after 实盘 sub ==')
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown > 40: break
