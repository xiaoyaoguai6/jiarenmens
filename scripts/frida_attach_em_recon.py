"""
Attach-only Frida controller for East Money recon.
EM APP MUST already be running (launched via `monkey` / am).

Captures all frida messages to data/recon/frida.log.
Run this in foreground (or background via Start-Job) AFTER manually opening EM.
Press Ctrl+C to stop.
"""
import json
import signal
import sys
import time
from pathlib import Path

import frida

TARGET_IDENTIFIER = "com.eastmoney.android.berlin"
SCRIPT_PATH = Path(__file__).resolve().parent / "frida_recon_em.js"
LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "recon" / "frida.log"

started_at = time.time()


def on_message(message, data):
    line = {"ts": time.time(), "elapsed": time.time() - started_at}
    if message.get("type") == "send":
        line["data"] = message.get("payload", {})
    elif message.get("type") == "error":
        line["error"] = {
            "description": message.get("description"),
            "stack": message.get("stack"),
            "fileName": message.get("fileName"),
        }
    else:
        line["other"] = message
    serialized = json.dumps(line, ensure_ascii=False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(serialized + "\n")
    print(serialized, flush=True)


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")

    device = frida.get_usb_device(timeout=5)
    print(f"[*] device id={device.id} name={device.name}", flush=True)

    try:
        session = device.attach(TARGET_IDENTIFIER)
    except frida.ProcessNotFoundError:
        print(f"[!] '{TARGET_IDENTIFIER}' not running; please start EM first.", flush=True)
        sys.exit(1)

    print(f"[*] attached to running {TARGET_IDENTIFIER}", flush=True)
    script_code = SCRIPT_PATH.read_text(encoding="utf-8")
    script = session.create_script(script_code)
    script.on("message", on_message)
    script.load()
    print(f"[*] hook injected. Operator: navigate in LDPlayer to a player's position page.", flush=True)
    print(f"[*] press Ctrl+C to stop and analyze data/recon/frida.log", flush=True)

    stop = {"v": False}
    def _stop(signum, frame): stop["v"] = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while not stop["v"]:
        time.sleep(0.5)
    print("\n[*] stopping", flush=True)
    try: session.detach()
    except Exception: pass
    print("[*] done", flush=True)


if __name__ == "__main__":
    main()