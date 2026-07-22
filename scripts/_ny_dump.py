import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml

adb = Adb()
print('focus:', adb.current_focus())
# tap bottom '自' tab at fixed coords 417-483 y 1857-1901 (确定 center ish 450, 1879)
adb.tap(450, 1879)
time.sleep(3)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_ny_after_zi.xml')
nodes = parse_ui_xml(xml)
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown >= 50: break
