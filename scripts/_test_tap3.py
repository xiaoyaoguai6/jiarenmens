import sys, time, os, json
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml

# Truncate positions.jsonl first to isolate this test
path = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(path): os.remove(path)
# also clear mitm log for clean trace
ml = r'D:\project\jiarenmens\data\recon\mitm.log'
if os.path.exists(ml): 
    try: os.truncate(ml, 0)
    except: pass

adb = Adb()
print('initial focus:', adb.current_focus())

print('* step 1: tap 调仓 tab')
ok = tap_text_if_present(adb, '调仓')
print(' ==>', ok)
time.sleep(3)
print('focus after tap:', adb.current_focus())
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_after_trade_tab.xml')
print('* step 2: tap 持仓 tab (return)')
ok = tap_text_if_present(adb, '持仓')
print(' ==>', ok)
time.sleep(3)
print('focus after tap back:', adb.current_focus())
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_back_hold_tab.xml')
print('* step 3: tap 历史收益')
ok = tap_text_if_present(adb, '历史收益')
print(' ==>', ok)
time.sleep(3)
print('focus after history:', adb.current_focus())
