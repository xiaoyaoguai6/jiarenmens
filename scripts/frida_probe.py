"""Minimal sanity check: attach to EM and probe whether the Java bridge works."""
import sys, time
import frida

device = frida.get_usb_device(timeout=5)
print("[*] device:", device.id, device.name, flush=True)

try:
    # Attach by exact process name, falling back to global walk.
    target_name = "com.eastmoney.android.berlin"
    # find pid via device.enumerate_applications
    pid = None
    for app in device.enumerate_applications():
        if app.identifier == target_name:
            pid = app.pid
            break
    if not pid:
        # try by process list
        for proc in device.enumerate_processes():
            if proc.name == target_name:
                pid = proc.pid
                break
    if not pid:
        print("[!] EM process not found by identifier or name", flush=True)
        sys.exit(1)
    print(f"[*] found pid={pid}", flush=True)
    session = device.attach(pid)
    print(f"[*] attached to pid={pid}", flush=True)
except frida.ProcessNotFoundError:
    print("[!] Attach failed with ProcessNotFoundError", flush=True)
    sys.exit(1)

# Try different ways to access Java to see what works in this frida version
probe = """
try {
    if (typeof Java === 'undefined') {
        send({stage: 'initial-check', result: 'Java is undefined'});
    } else {
        send({stage: 'initial-check', result: 'Java is defined'});
        Java.perform(function(){
            send({stage: 'inside-perform', result: 'Java.perform OK'});
            try {
                var WebView = Java.use('android.webkit.WebView');
                send({stage: 'lookup-WebView', result: 'got class'});
                try {
                    WebView.setWebContentsDebuggingEnabled(true);
                    send({stage: 'force-debug', result: 'setWebContentsDebuggingEnabled(true) succeeded'});
                } catch(e) { send({stage: 'force-debug', err: String(e)}); }
                try {
                    var RealCall = Java.use('okhttp3.RealCall');
                    send({stage: 'lookup-okhttp', result: 'got class'});
                } catch(e) { send({stage: 'lookup-okhttp', err: String(e)}); }
            } catch(e) {
                send({stage: 'lookup-failed', err: String(e)});
            }
        });
    }
} catch(e) {
    send({stage: 'toplevel-throw', err: String(e)});
}
"""

def on_msg(m, d):
    print("MSG:", m, flush=True)

script = session.create_script(probe)
script.on("message", on_msg)
print("[*] loading script ...", flush=True)
script.load()
print("[*] script loaded; waiting 8s", flush=True)
time.sleep(8)
session.detach()
print("[*] done", flush=True)