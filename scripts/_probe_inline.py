import frida, time
device = frida.get_usb_device(timeout=5)
pid = device.spawn(['com.eastmoney.android.berlin'])
print('spawned', pid)
session = device.attach(pid)
js = open(r'D:\project\jiarenmens\scripts\probe_globals.js','r',encoding='utf-8').read()
script = session.create_script(js)
def on_msg(m,d):
    print('MSG:', m.get('type'), '-', m.get('payload') or m.get('description') or '')
script.on('message', on_msg)
script.load()
device.resume(pid)
time.sleep(4)
session.detach()
