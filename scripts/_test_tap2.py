import sys, json, time
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, parse_ui_xml, dump_to_file

adb = Adb()
print('focus:', adb.current_focus())

# Take screenshot
adb.screenshot(r'D:\project\jiarenmens\data\recon\after_tap.png')
print('screenshot saved')

# Dump current UI
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_state_tap_after.xml')
nodes = parse_ui_xml(xml)
print(f'total nodes: {len(nodes)}')
print('=== first 30 nodes with text ===')
shown = 0
for n in nodes:
    if n['text']:
        print(f'  text={n["text"][:40]:42s} bounds={n["bounds"]}')
        shown += 1
        if shown >= 30:
            break
