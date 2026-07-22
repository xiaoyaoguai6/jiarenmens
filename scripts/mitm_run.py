"""Run mitmdump inline (in this Python process) so we see startup errors.

Truncates mitm.log on start.  Stays alive until SIGTERM/SIGKILL.
"""
import asyncio
import sys
from pathlib import Path

from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mitm_em_position_extractor as addon_mod  # noqa: E402

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"
LOG_PATH = RECON_DIR / "mitm.log"
ERR_PATH = RECON_DIR / "mitm.err.log"
LOG_PATH.write_text("")
ERR_PATH.write_text("")


async def serve():
    addon = addon_mod.PositionExtractorAddon()
    opts = options.Options()
    opts.listen_host = "0.0.0.0"
    opts.listen_port = 8080
    m = DumpMaster(options=opts, with_dumper=True)
    m.addons.add(addon)
    # DumpMaster already adds a Save addon; just enable + point it at our file:
    m.options.update(save_stream_file=str(RECON_DIR / "realtime.flows"))
    print(f"[*] addons attached (incl Save -> realtime.flows)", flush=True)
    print(f"[*] listening 0.0.0.0:8080 (with_dumper=True) ... (log={LOG_PATH})", flush=True)
    await m.run()


if __name__ == "__main__":
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("[*] stopped", flush=True)