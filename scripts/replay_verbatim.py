"""Replay one captured rtV3 request VERBATIM (headers + body + sign) to isolate
whether the 9081 code is caused by missing sign or by risk-control/IP.

If verbatim replay succeeds -> sign is mandatory and is per-request.
If verbatim replay still returns 9081 (or different code) -> 9081 is risk-control,
caused by IP mismatch / replay-detection / token race.

This is critical because it determines the only remaining implementation route.
"""
import json
import random
import string
import time
from pathlib import Path

import requests

FLOWS = Path(r"D:\project\jiarenmens\data\recon\em.flows")

# Pick first complete rtV3 request with method=CombinationHoldPositionPermitHandler or info
samples = []
for line in FLOWS.read_text(encoding="utf-8").splitlines():
    try:
        rec = json.loads(line)
    except Exception:
        continue
    if rec.get("host") != "spzhapi.dfcfs.cn":
        continue
    if rec.get("phase") != "request":
        continue
    headers = rec.get("headers", {})
    body = rec.get("body")
    if not headers.get("sign") or not body:
        continue
    samples.append({"headers": headers, "body": body})

print(f"Captured {len(samples)} rtV3 requests with sign")

# Find one for CombinationInfoHandler, and one for CombinationHoldPositionPermitHandler
def pick(method):
    for s in samples:
        if f'"method":"{method}"' in s["body"]:
            return s
    return None

for target_method in ("CombinationInfoHandler", "CombinationHoldPositionPermitHandler"):
    s = pick(target_method)
    if not s:
        print(f"\n[skip] no capture for {target_method}")
        continue
    print("\n" + "="*70)
    print(f"=== VERBATIM REPLAY for {target_method} ===")
    body = s["body"]
    headers = dict(s["headers"])
    # we keep requestid and sign as-is to test verbatim reproducibility
    print(f"sign={headers.get('sign')[:32]}...")
    print(f"requestid={headers.get('requestid')}")
    print(f"body head: {body[:200]}")
    r = requests.post("https://spzhapi.dfcfs.cn/rtV3", headers=headers, data=body.encode("utf-8"), timeout=15)
    print(f"-> status={r.status_code} bytes={len(r.content)}")
    print(r.text[:1000])