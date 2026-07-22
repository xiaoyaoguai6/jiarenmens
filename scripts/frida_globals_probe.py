"""Probe the frida JS environment for available globals in native (default) spawn realm."""
import time, frida

device = frida.get_usb_device(timeout=5)
print("[*] device:", device.id, flush=True)

pid = device.spawn(["com.eastmoney.android.berlin"])
print(f"[*] spawned pid={pid}", flush=True)
session = device.attach(pid)
script = session.create_script("""
console.log('=== globals ===');
console.log(Object.keys(globalThis).filter(k => /^(Java|ObjC|Process|Frida|Module|ObjCRef|iObjCRef|Instruction)/.test(k || '')).join(','));
console.log('typeof Java=', typeof Java);
console.log('typeof ObjC=', typeof ObjC);
console.log('typeof Process=', typeof Process);
console.log('typeof Module=', typeof Module);
console.log('typeof Interceptor=', typeof Interceptor);
console.log('typeof File=', typeof File);
console.log('archs:', Process.arch, 'pid:', Process.id);

const ac = process.arch === 'x64' ? 64 : 32;
console.log('arch x64:', Process.arch === 'x64');

// Check Realm awareness
try {
  send({stage:'probe', env: Object.keys(globalThis).slice(0,80)});
} catch(e) {
  send({stage:'throw', err: String(e)});
}
""")

def on_msg(m, d):
    print("MSG:", m, flush=True)

script.on("message", on_msg)
script.load()
print("[*] script loaded, resuming pid", flush=True)
device.resume(pid)
time.sleep(5)
try:
    session.detach()
except Exception: pass
print("[*] done", flush=True)