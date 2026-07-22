import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml

adb = Adb()
print('focus:', adb.current_focus())

p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

# wait for app settle
time.sleep(3)

# Find what tabs UI shows
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_current_dump.xml')
nodes = parse_ui_xml(xml)
print('=== ALL text nodes ===')
shown=0
for n in nodes:
    if n['text'] and len(n['text']) > 0:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
