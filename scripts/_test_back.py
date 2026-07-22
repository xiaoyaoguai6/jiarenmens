import sys, time, os, json
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml, find_node, bounds_to_xy

# Truncate positions.jsonl
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

adb = Adb()
print('focus:', adb.current_focus())

# Press back to leave combination detail
print('=== press_back x 2 ===')
adb.press_back(); time.sleep(1)
adb.press_back(); time.sleep(2)
print('focus:', adb.current_focus())

# Now look at home page
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_back_home.xml')
nodes = parse_ui_xml(xml)
print(f'== nodes {len(nodes)} ==')
for n in nodes[:25]:
    if n['text']:
        print(f'  text={n["text"][:40]} bounds={n["bounds"]}')

# Tap 实盘 tab if present
print('=== tap 实盘 ===', tap_text_if_present(adb, '实盘'))
time.sleep(2)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_after_shipan.xml')
nodes = parse_ui_xml(xml)
print(f'== nodes {len(nodes)} ==')
for n in nodes[:30]:
    if n['text']:
        print(f'  text={n["text"][:40]} bounds={n["bounds"]}')
