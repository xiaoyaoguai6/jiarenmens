import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml, find_node, bounds_to_xy

p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

adb = Adb()
print('=== tap 晒网打大 (zhid=900083077) ===')
ok = tap_text_if_present(adb, '晒网打大')
print('  ->', ok)
time.sleep(6)  # give time for rtV3 calls + RN render
print('focus after tap:', adb.current_focus())

xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_after_player_tap.xml')
nodes = parse_ui_xml(xml)
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown > 40: break
