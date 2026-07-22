"""
Frida spawn-and-log controller for East Money recon.

Spawns com.eastmoney.android.berlin with hook script, captures every frida
message to data/recon/frida.log, and keeps the session alive until the operator
presses Ctrl+C.

Usage:
    python scripts/frida_run_em_recon.py
Then operate the APP in LDPlayer. Press Ctrl+C to stop.
"""
import json
import sys
import time
import signal
from pathlib import Path

import frida

TARGET = "com.eastmoney.android.berlin"
SCRIPT_PATH = Path(__file__).resolve().parent / "frida_recon_em.js"
LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "recon" / "frida.log"

started_at = time.time()


def on_message(message, data):
    """Frida -> Python callback. Persist every message + show summary."""
    line = {
        "ts": time.time(),
        "elapsed": time.time() - started_at,
    }
    if message.get("type") == "send":
        payload = message.get("payload", {})
        if isinstance(payload, (dict, list)):
            line["data"] = payload
        else:
            line["data"] = {"raw": str(payload)}
    elif message.get("type") == "log":
        line["console"] = message.get("payload", "")
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

    # Also echo to stdout for live tail
    print(serialized, flush=True)


def main():
    # fresh log
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")
    print(f"[*] log -> {LOG_PATH}", flush=True)

    device = frida.get_usb_device(timeout=5)
    print(f"[*] device id={device.id} name={device.name}", flush=True)

    print(f"[*] spawning {TARGET}", flush=True)
    pid = device.spawn([TARGET])
    print(f"[*] spawned pid={pid}", flush=True)

    session = device.attach(pid)
    script_code = SCRIPT_PATH.read_text(encoding="utf-8")
    script = session.create_script(script_code)
    script.on("message", on_message)
    script.load()
    device.resume(pid)
    print(f"[*] hook injected, APP resumed. Operator: navigate in LDPlayer.", flush=True)
    print(f"[*] press Ctrl+C to stop", flush=True)

    # wait until Ctrl+C
    stop = False
    def _stop(signum, frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while not stop:
        time.sleep(0.5)

    print("\n[*] stopping", flush=True)
    try:
        session.detach()
    except Exception as e:
        print(f"detach err: {e}", flush=True)
    try:
        device.kill(pid)
    except Exception as e:
        print(f"kill err: {e}", flush=True)
    print("[*] done", flush=True)


if __name__ == "__main__":
    main()