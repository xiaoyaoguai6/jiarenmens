import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml, find_node, bounds_to_xy

adb = Adb()
# Need to switch to berlin app's Home. Just relaunch launcher.
# stop newyork and ensure berlin is active
import subprocess
subprocess.run([r'C:\leidian\LDPlayer9\adb.exe','-s','emulator-5554','shell','am','force-stop','com.eastmoney.android.newyork'])
time.sleep(1)
subprocess.run([r'C:\leidian\LDPlayer9\adb.exe','-s','emulator-5554','shell','monkey','-p','com.eastmoney.android.berlin','-c','android.intent.category.LAUNCHER','1'], capture_output=True)
time.sleep(4)
print('focus:', adb.current_focus())

# Truncate positions.jsonl
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

# tap bottom 自选 - exact match
ok = tap_text_if_present(adb, '自选')
print('tap 自选 ->', ok)
time.sleep(2)
print('focus now:', adb.current_focus())

# After Self selected (子 self select), tap 实盘 sub-tab
ok = tap_text_if_present(adb, '实盘')
print('tap 实盘 ->', ok)
time.sleep(2)

# Dump to find player names in the list
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_shipan_list_v2.xml')
nodes = parse_ui_xml(xml)
print('== text nodes in 实盘 list tab ==')
shown = 0
for n in nodes:
    if n['text'] and len(n['text']) > 1:
        print(f'  text={n["text"][:50]:52s} bounds={n["bounds"]}')
        shown += 1
        if shown > 30: break

# find first player name and tap it (the text 囊 e.g. 晒网打大)
# Try a hash-bang partial
ok = tap_text_if_present(adb, '晒网')
print('tap 晒网 ->', ok)  # might not match because text gets sliced by encoding
time.sleep(6)
print('focus after player tap:', adb.current_focus())
