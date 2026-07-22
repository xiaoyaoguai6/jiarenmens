import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml

# Truncate positions.jsonl to isolate the test
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

adb = Adb()
print('=== tap 我的 sub-tab ===', tap_text_if_present(adb, '我的'))
time.sleep(2)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_wode.xml')
nodes = parse_ui_xml(xml)
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:40]:42s} bounds={n["bounds"]}')
        shown += 1
        if shown > 40: break
