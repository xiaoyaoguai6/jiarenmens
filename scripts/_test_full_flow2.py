import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml

adb = Adb()
print('focus:', adb.current_focus())

# Make sure we're at home (press back enough)
for _ in range(5):
  adb.press_back(); time.sleep(0.5)
print('focus after 5 backs:', adb.current_focus())

# Truncate positions.jsonl so we see only new events
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

# tap 自选 (bottom tab)
ok = tap_text_if_present(adb, '自')
print('tap 自 ->', ok)
time.sleep(2)

# after going to 自选 tab, dump UI
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_zixuan_dump.xml')
nodes = parse_ui_xml(xml)
shown = 0
for n in nodes:
    if n['text'] and len(n['text']) > 1:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown > 30: break
