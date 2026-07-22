import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, dump_to_file, parse_ui_xml, tap_text_if_present

adb = Adb()
print('focus before:', adb.current_focus())
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

# Tap bottom 自选 tab at fixed coords
adb.tap(450, 1879)
time.sleep(2)
print('focus after 自选 tap:', adb.current_focus())

# Dump UI to confirm we are in "自选/实盘榜" view
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_zixuan_real.xml')
nodes = parse_ui_xml(xml)
print('== text nodes after 自选 tap ==')
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown > 40: break

# Then tap 实盘 sub-tab
ok = tap_text_if_present(adb, '实盘')
print('tap 实盘 ->', ok)
time.sleep(2)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_shipan_v3.xml')
nodes = parse_ui_xml(xml)
print('== text nodes after 实盘 ==')
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown > 40: break

# Tap the visible "晒网打大" entry. The bounds were [45,1330][372,1510]
# tap its center
adb.tap(208, 1420)  # try first row of player names below
time.sleep(6)
print('focus after tap 晒网打大 center:', adb.current_focus())
