import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml

adb = Adb()
print('=== tap 自选 (bottom tab, partial match) ===', tap_text_if_present(adb, '自选'))
time.sleep(2)
print('=== tap 自选 prefix char ===')  # partial
ok = tap_text_if_present(adb, '自')
print('  ', ok)
time.sleep(1)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_zixuan.xml')
nodes = parse_ui_xml(xml)
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:40]:42s} bounds={n["bounds"]}')
        shown += 1
        if shown > 40: break
