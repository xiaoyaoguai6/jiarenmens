import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, dump_to_file, parse_ui_xml

adb = Adb()
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_now.xml')
nodes = parse_ui_xml(xml)
print('=== nodes with content_desc ===')
for n in nodes:
    if n['content_desc']:
        print(f'  text={n["text"][:30]:32s} content_desc={n["content_desc"][:40]:42s} bounds={n["bounds"]}')
