import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, dump_to_file, parse_ui_xml

adb = Adb()
print('focus:', adb.current_focus())
adb.screenshot(r'D:\project\jiarenmens\data\recon\home_full.png')
nodes = parse_ui_xml(dump_to_file(adb, r'D:\project\jiarenmens\data\recon\home_dump.xml'))
print(f'== ALL TEXT nodes (n={len(nodes)}) ==')
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:60]:62s} bounds={n["bounds"]}')
        shown += 1
print('---WITH TEXT COUNT:', shown)
