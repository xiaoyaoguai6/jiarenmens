import sys, time
sys.path.insert(0, r'D:\project\jiarenmens\scripts')
from adb_ui import Adb, tap_text_if_present, dump_to_file
adb = Adb()
print('focus:', adb.current_focus())

xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_state_before_tap.xml')
print('dump initial xml saved')

print('--- tap 持仓详情 ---')
ok = tap_text_if_present(adb, '持仓详情')
print('tap 持仓详情 ->', ok)

time.sleep(3)
xml = dump_to_file(adb, r'D:\project\jiarenmens\data\recon\ui_state_after_tap.xml')
print(f'after-tap focus: {adb.current_focus()}')
