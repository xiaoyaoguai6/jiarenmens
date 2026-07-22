"""
EM recon via Frida SPAWN (not attach) — pre-main hook inject + emulated realm.

Args:
    --duration N        auto-quit after N seconds (default 90)
    --log PATH          frida log path (data/recon/frida.log)
Anti-debug:
    EM apps detect late frida attach by ptrace self-kill SIG9.  By spawning
    the APP ourselves we run the script before its anti-debug init touches ptrace.
    Combined with realm='emulated' the Java bridge becomes available.
"""
import argparse
import json
import signal
import sys
import time
from pathlib import Path

import frida

TARGET = "com.eastmoney.android.berlin"
SCRIPT_PATH = Path(__file__).resolve().parent / "frida_recon_em.js"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=int, default=90,
                   help="auto-quit after N seconds")
    p.add_argument("--log", type=Path,
                   default=Path(__file__).resolve().parent.parent / "data" / "recon" / "frida.log")
    return p.parse_args()


def main():
    args = parse_args()
    log_path: Path = args.log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("")
    started_at = time.time()

    def on_message(m, d):
        line = {
            "ts": time.time(),
            "elapsed": time.time() - started_at,
            "type": m.get("type"),
            "payload": m.get("payload"),
            "stack": m.get("stack"),
            "fileName": m.get("fileName"),
        }
        serialized = json.dumps(line, ensure_ascii=False, default=str)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(serialized + "\n")
        print(serialized, flush=True)

    device = frida.get_usb_device(timeout=5)
    print(f"[*] device id={device.id} name={device.name}", flush=True)

    print(f"[*] spawning {TARGET} (frida spawns before ART runs EM main)", flush=True)
    pid = device.spawn([TARGET])
    print(f"[*] spawned pid={pid}", flush=True)

    # attach BEFORE resume so our install scripts run prior to EM's anti-debug init
    session = device.attach(pid)
    script_code = SCRIPT_PATH.read_text(encoding="utf-8")
    script = session.create_script(script_code)
    script.on("message", on_message)
    print("[*] loading hook script ...", flush=True)
    script.load()
    print(f"[*] hook loaded; now resuming target pid={pid}", flush=True)
    device.resume(pid)
    print(f"[*] target resumed. Log -> {log_path}", flush=True)
    print(f"[*] auto-detach after {args.duration} s — operate EM in LDPlayer now", flush=True)

    end = time.time() + args.duration
    stop = {"v": False}
    def _stop(signum, frame): stop["v"] = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while not stop["v"] and time.time() < end:
        time.sleep(0.4)
    print(f"\n[*] elapsed {time.time()-started_at:.1f}s, detaching", flush=True)
    try: session.detach()
    except Exception: pass
    print("[*] done", flush=True)


if __name__ == "__main__":
    main()