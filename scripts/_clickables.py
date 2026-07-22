import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, dump_to_file, parse_ui_xml

adb = Adb()
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_ny_now.xml')
nodes = parse_ui_xml(xml)
print('=== clickable=True nodes with text ===')
for n in nodes:
    if n['text'] and 'clickable="true"' in xml[:]:
        pass

# easier: regex extract clickable=true with surrounding text nearby
import re
clickables = re.findall(r'<node[^>]*clickable="true"[^>]*?text="([^"]*)"[^>]*?bounds="(\[\d+,\d+\]\[\d+,\d+\])"', xml)
for t, b in clickables:
    if t:
        print(f'  text={t[:30]:32s} bounds={b}')
