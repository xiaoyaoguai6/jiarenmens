"""Decide whether the captured `sign` header is body-agnostic (only validates
token/state) or body-binding (requires regenerating sign for each new body).

Strategy (uses verbatim replay infrastructure):
1) Take a captured CombinationInfoHandler request with sign `S_sign`, body `B1`.
   Replay verbatim (proven to succeed in our last test).
2) Take S_sign and **delete one byte** in the body (or swap combinationId for
   a DIFFERENT zh_id, change the timestamp to NOW) so the body string differs.
   Still send the SAME S_sign in header.
3) Outcomes:
   a) Success -> sign is body-agnostic. Then can package-swap any zhid.
   b) Fail with code 9081 -> sign is body-binding. Cannot reuse across bodies.

For cross-method test, also use a CombinationHoldPositionPermitHandler's
sign on CombinationInfoHandler body to confirm cross-method failure.
"""
import hashlib
import json
import random
import re
import string
import time
from pathlib import Path

import requests

FLOWS = Path(r"D:\project\jiarenmens\data\recon\em.flows")
ENDPOINT = "https://spzhapi.dfcfs.cn/rtV3"

samples_by_method = {}
for line in FLOWS.read_text(encoding="utf-8").splitlines():
    try:
        rec = json.loads(line)
    except Exception:
        continue
    if rec.get("host") != "spzhapi.dfcfs.cn" or rec.get("phase") != "request":
        continue
    h = rec.get("headers", {})
    body = rec.get("body")
    if not h.get("sign") or not body:
        continue
    m = re.search(r'"method":"([^"]+)"', body)
    if m and m.group(1) not in samples_by_method:
        samples_by_method[m.group(1)] = {
            "sign": h["sign"],
            "requestid": h.get("requestid"),
            "body": body,
        }

# Need CombinationInfoHandler success samples (verbatim replay returned Success previously)
info = samples_by_method.get("CombinationInfoHandler")
pos = samples_by_method.get("CombinationHoldPositionPermitHandler")
print("available samples:", list(samples_by_method.keys()))
if info:
    print("\nInfo sample sign:", info["sign"][:32], "...")
    print("Info sample body head:", info["body"][:200])
    print("Info sample ts/randomCode:",
          re.search(r'"timestamp":(\d+)', info["body"]).group(1),
          re.search(r'"randomCode":"([^"]+)"', info["body"]).group(1))


def post(sign, body, requestid=None):
    headers = {
        "accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "okhttp/3.12.13",
        "Host": "spzhapi.dfcfs.cn",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "appversion": "11.1.5",
        "rnversion": "2.2.0.260626112525513",
        "sign": sign,
        "requestid": requestid or f"test{int(time.time()*1000)}",
    }
    r = requests.post(ENDPOINT, headers=headers, data=body.encode("utf-8"), timeout=15)
    return r.status_code, r.text


def make_rand():
    return "".join(random.choices(string.ascii_letters + string.digits, k=25))

# ---------------- 1) VERBATIM BASELINE (sanity check) ----------------
print("\n=== TEST 1: verbatim replay (must succeed) ===")
code, txt = post(info["sign"], info["body"], info["requestid"])
print(f"status={code} text={txt[:300]}")

# ---------------- 2) Same body, DIFFERENT requestid (pure test) ----------------
print("\n=== TEST 2: same body+sign, only requestid different ===")
code, txt = post(info["sign"], info["body"], f"NEW{int(time.time()*1000)}")
print(f"status={code} text={txt[:300]}")

# ---------------- 3) Same body as info, but change timestamp+randomCode to NOW/hot----
print("\n=== TEST 3: change only timestamp & randomCode (keep body else) ===")
new_body = re.sub(r'"timestamp":\d+', f'"timestamp":{int(time.time()*1000)}', info["body"])
new_body = re.sub(r'"randomCode":"[^"]+"', f'"randomCode":"{make_rand()}"', new_body)
code, txt = post(info["sign"], new_body, info["requestid"])
print(f"status={code} text={txt[:300]}")

# ---------------- 4) Change combinationId to a DIFFERENT zhid ----------------
print("\n=== TEST 4: change combinationId only (sign stays) ===")
new_body = re.sub(r'"combinationId":"?(\d+)"?', '"combinationId":"900296556"',
                  info["body"])
# also refresh ts/rc just to be safe
new_body = re.sub(r'"timestamp":\d+', f'"timestamp":{int(time.time()*1000)}', new_body)
new_body = re.sub(r'"randomCode":"[^"]+"', f'"randomCode":"{make_rand()}"', new_body)
code, txt = post(info["sign"], new_body, info["requestid"])
print(f"  new_body head: {new_body[:200]}")
print(f"  status={code} text={txt[:300]}")

# ---------------- 5) Cross-method: info-body but pos-sign ----------------
print("\n=== TEST 5: cross-method (info body + pos sign) ===")
code, txt = post(pos["sign"], info["body"], info["requestid"])
print(f"status={code} text={txt[:300]}")

# ---------------- 6) Body Compaction: minify whitespace as okhttp sends---------------
# okhttp sends compact JSON, so our body should already be compact

# ---------------- 7) Crucial: strip sign header completely ----------------
print("\n=== TEST 7: NO sign header ===")
code, txt = post("", info["body"], info["requestid"])
print(f"status={code} text={txt[:300]}")

# ---------------- 8) Wrong sign completely ----------------
print("\n=== TEST 8: wrong (random 64 hex) sign ===")
bad_sign = "f" * 64
code, txt = post(bad_sign, info["body"], info["requestid"])
print(f"status={code} text={txt[:300]}")