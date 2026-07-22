import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml, find_node, bounds_to_xy

p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

adb = Adb()
# first tap 实盘 sub-tab
print('=== tap 实盘 subtab ===', tap_text_if_present(adb, '实盘'))
time.sleep(2)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_shipan_list.xml')
nodes = parse_ui_xml(xml)
# look for player names
print('first text nodes after 实盘 tap:')
shown=0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:40]:42s} bounds={n["bounds"]}')
        shown += 1
        if shown > 50: break
# Tap first entry's container (will find_node by text contains 晒)
print('=== tap 晒 ===', tap_text_if_present(adb, '晒'))
time.sleep(6)
print('focus after tap:', adb.current_focus())
