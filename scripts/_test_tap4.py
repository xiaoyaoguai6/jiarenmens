import sys, time, os
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file

# Truncate positions.jsonl to only new events
p = r'D:\project\jiarenmens\data\recon\positions.jsonl'
if os.path.exists(p): os.remove(p)

adb = Adb()
print('focus:', adb.current_focus())

# Trigger rtV3 by tapping the holding/trade tabs
import time
print('=== tap 调仓 ===', tap_text_if_present(adb, '调仓'))
time.sleep(2.5)
print('=== tap 持仓 ===', tap_text_if_present(adb, '持仓'))
time.sleep(2.5)
print('=== tap 历史收益 ===', tap_text_if_present(adb, '历史收益'))
time.sleep(2.5)
print('=== tap 证券持仓 ===', tap_text_if_present(adb, '证券持仓'))
time.sleep(2.5)
