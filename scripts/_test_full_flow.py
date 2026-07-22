import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file
adb = Adb()
# remove old events
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)
print('focus now:', adb.current_focus())
# exit any activity to ensure we can re-enter
for _ in range(2):
  adb.press_back(); time.sleep(0.6)
print('after back:', adb.current_focus())
# tap 自选
print('=== tap 自选 partial ===', tap_text_if_present(adb, '自') is not False or tap_text_if_present(adb, '自选'))
time.sleep(2)
# tap 实盘 sub
print('=== tap 实盘 ===', tap_text_if_present(adb, '实盘'))
time.sleep(2)
# tap 晒
print('=== tap 晒 partial ===', tap_text_if_present(adb, '晒'))
time.sleep(6)
print('final focus:', adb.current_focus())
