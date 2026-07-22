"""Collect all spzhapi rtV3 requests with their sign + body and try common
EM signing formulas to brute-force crack the algorithm.

Output: data/recon/sign_analysis.json
"""
import hashlib
import json
import re
from pathlib import Path

FLOWS = Path(r"D:\project\jiarenmens\data\recon\em.flows")

# Each request has headers.sign + body (a JSON string)
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
    sign = headers.get("sign")
    if not sign:
        continue
    body = rec.get("body")
    if not body:
        continue
    # Parse body to get ordered fields as far as the server cares
    try:
        parsed = json.loads(body)
    except Exception:
        continue
    samples.append({
        "sign": sign,
        "requestid": headers.get("requestid"),
        "raw_body": body,
        "parsed": parsed,
        "timestamp": parsed.get("timestamp"),
        "randomCode": parsed.get("randomCode"),
        "method": parsed.get("method"),
        "client": parsed.get("client"),
        "clientType": parsed.get("clientType"),
        "clientVersion": parsed.get("clientVersion"),
        "deviceId": parsed.get("deviceId"),
        "args": parsed.get("args"),
    })

print(f"Collected {len(samples)} samples")
for s in samples[:8]:
    print(f"\n--- sample ---")
    print(f"  sign={s['sign']}")
    print(f"  requestid={s['requestid']}")
    print(f"  ts={s['timestamp']} rc={s['randomCode']} method={s['method']}")
    print(f"  body={s['raw_body'][:200]}")

# Try common EM signing formulas.
# Format hypothesis: SHA256(concat(fields) + salt)
# Common eastmoney salts in past RE attempts: 'c612d1c8-3d4d-4f1f', 'owa!f3lM2$f4l%'
# Or sha256 of "method|timestamp|randomCode|deviceId|secretyKey"
# Or sha256 of full body (no salt)
# Or sha256 of "body|requestid"

candidates = []

def test(name, fn, samples):
    matched = 0
    for s in samples[:8]:
        candidate = fn(s)
        if candidate == s["sign"]:
            matched += 1
    if matched > 0:
        print(f"[{'HIT' if matched==min(8,len(samples)) else 'PARTIAL'}] {name}: matched {matched}/{min(8,len(samples))}")
        candidates.append((name, matched, fn))
    return matched

# 1: plain body
test("sha256(body)", lambda s: hashlib.sha256(s["raw_body"].encode("utf-8")).hexdigest(), samples)

# 2: body with trailing newline / no
test("sha256(body + '\\n')", lambda s: hashlib.sha256((s["raw_body"] + "\n").encode()).hexdigest(), samples)

# 3: common field concatenations
def f_concat_fields(s, sep=""):
    p = s["parsed"]
    # canonical: args dict serialized, then method/randomCode/timestamp/deviceId/client
    args_json = json.dumps(p["args"], separators=(",", ":"), ensure_ascii=False)
    return sep.join([
        args_json,
        p["method"],
        p["randomCode"],
        str(p["timestamp"]),
        p["deviceId"],
        p["client"],
        p["clientType"],
        p["clientVersion"],
    ])
test("concat args+method+rc+ts+deviceId+client+type+ver (no sep)",
     lambda s: hashlib.sha256(f_concat_fields(s).encode()).hexdigest(), samples)
test("concat args+method+rc+ts+deviceId+client+type+ver (| sep)",
     lambda s: hashlib.sha256(f_concat_fields(s, "|").encode()).hexdigest(), samples)

# 4: just method|randomCode|timestamp|deviceId
def f_mini(s):
    p = s["parsed"]
    return "|".join([p["method"], p["randomCode"], str(p["timestamp"]), p["deviceId"]])
test("sha256(method|rc|ts|deviceId)",
     lambda s: hashlib.sha256(f_mini(s).encode()).hexdigest(), samples)

# 5: sha256(method + args)  (no rc/ts)
def f_method_args(s):
    p = s["parsed"]
    args_json = json.dumps(p["args"], separators=(",",":"), ensure_ascii=False)
    return p["method"] + args_json
test("sha256(method+args_json_compact)",
     lambda s: hashlib.sha256(f_method_args(s).encode()).hexdigest(), samples)

# 6: try with common static salt prefixes/suffixes
SALTS = [
    "", "c612d1c8-3d4d-4f1f",
    "82f90d6f6c8d4cf7a9f12c337c2c33f1",  # dummy guess
    "dfcft_secret", "emceemsecretkey", "fcsantt0o",
    "78cd8b44c98a9d9a75ef0ab107e0f3c7",  # from first sign prefix (doubtful)
    "secret", "owa!f3lM2$f4l%",
]
for salt in SALTS:
    def f_salt(s, salt=salt):
        return hashlib.sha256((s["raw_body"] + salt).encode("utf-8")).hexdigest()
    test(f"sha256(body+{salt!r:.30})", f_salt, samples)
    def f_salt_pre(s, salt=salt):
        return hashlib.sha256((salt + s["raw_body"]).encode("utf-8")).hexdigest()
    test(f"sha256({salt!r:.30}+body)", f_salt_pre, samples)

# 7: try args-only sign (most EM apps sign just the args JSON)
def f_args_only(s, salt=""):
    p = s["parsed"]
    args_json = json.dumps(p["args"], separators=(",",":"), ensure_ascii=False)
    return hashlib.sha256((args_json + salt).encode()).hexdigest()
for salt in ["", "dfcft_secret", "82f90d6f6c8d4cf7a9f12c337c2c33f1"]:
    test(f"sha256(args_compact+{salt!r:.20})", lambda s,sl=salt: f_args_only(s, sl), samples)

# 8: MD5-based as fallback (32 chars), HMAC-SHA256 (api_secret)
# But sign is 64 chars = SHA256 plain only.

print(f"\nTotal unique candidate formulas tested: {len(candidates)} hits")
out = {
    "samples": [{"sign": s["sign"], "raw_body": s["raw_body"], "requestid": s["requestid"]} for s in samples],
    "candidates_with_hits": [{"name":n,"matched":m} for n,m,_ in candidates],
}
Path(r"D:\project\jiarenmens\data\recon\sign_analysis.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote data/recon/sign_analysis.json")