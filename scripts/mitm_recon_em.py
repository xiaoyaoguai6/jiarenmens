"""
mitmproxy recon: capture East Money APP HTTPS traffic to data/recon/em.flows.

When invoked via `mitmdump -s this_script.py`, mitmproxy reads the top-level
`addons` list and registers ReconAddon automatically.  There is no need to run
this file as a python script.

Filter: keeps only requests whose host contains one of: eastmoney / dfcf /
emcdn / dcfs.  Writes a JSON line per request/response to
data/recon/em.flows for easy post-processing.
"""
import json
import time
from pathlib import Path

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"
RECON_DIR.mkdir(parents=True, exist_ok=True)

FLOWS_JSONL = RECON_DIR / "em.flows"

INTERESTING_KEYS = ("eastmoney", "dfcf", "emcdn", "dcfs")


def is_interesting(host: str) -> bool:
    if not host:
        return False
    h = host.lower()
    return any(k in h for k in INTERESTING_KEYS)


class ReconAddon:
    """writes only web/https flows with EM-related hosts to em.flows"""

    def request(self, flow):
        host = flow.request.host or ""
        if not is_interesting(host):
            return
        # Capture POST/PUT body for hosts in API family (rtV2 endpoints especially)
        body_preview = None
        if flow.request.method in ("POST", "PUT", "PATCH"):
            try:
                body_preview = flow.request.get_text(strict=False) or ""
                body_preview = body_preview[:5000]
            except Exception:
                body_preview = "<binary>"
        line = {
            "ts": time.time(),
            "phase": "request",
            "method": flow.request.method,
            "url": flow.request.url,
            "host": host,
            "path": flow.request.path,
            "headers": dict(flow.request.headers),
            "body": body_preview,
        }
        self.append(line)

    def response(self, flow):
        host = flow.request.host or ""
        if not is_interesting(host):
            return
        try:
            body_text = flow.response.get_text(strict=False)
            body_preview = (body_text or "")[:5000]
        except Exception:
            body_preview = "<binary>"
        line = {
            "ts": time.time(),
            "phase": "response",
            "method": flow.request.method,
            "url": flow.request.url,
            "host": host,
            "path": flow.request.path,
            "status": flow.response.status_code,
            "len": len(flow.response.content) if flow.response.content else 0,
            "headers": dict(flow.response.headers),
            "body_preview": body_preview,
        }
        self.append(line)

    @staticmethod
    def append(line):
        serialized = json.dumps(line, ensure_ascii=False, default=str)
        with FLOWS_JSONL.open("a", encoding="utf-8") as f:
            f.write(serialized + "\n")
        print(serialized, flush=True)


addons = [ReconAddon()]