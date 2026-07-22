"""Pair rtV3 requests with their responses from em.flows and dump by method."""
import json
import re
from pathlib import Path

FLOWS = Path(r"D:\project\jiarenmens\data\recon\em.flows")

# Collect all rtV3 events in order with index so we can pair request/response naturally
# (mitmproxy emits request then response for the same flow; requests alternate with
# responses on the same host+ts sweep)
events = []
for line in FLOWS.read_text(encoding="utf-8").splitlines():
    try:
        rec = json.loads(line)
    except Exception:
        continue
    if rec.get("host") != "spzhapi.dfcfs.cn":
        continue
    events.append(rec)

# Group consecutive request/response pairs by ts proximity (<5s) and same pairing.
# Simpler: process in pairs as they appear (request, response, request, response).
requests = [e for e in events if e.get("phase") == "request"]
responses = [e for e in events if e.get("phase") == "response"]

# Match by index assuming 1:1 ordering: requests and responses are emitted in pairs.
# However other hosts' flows interleave; here we've already filtered to spzhapi only.
# So requests[i] ~ responses[i] (mitmproxy is sequential per host).
buckets = {
    "CombinationHoldPositionPermitHandler": [],
    "CombinationRelocatePositionHandler": [],
    "CombinationHoldBlockPermitHandler": [],
    "CombinationInfoHandler": [],
    "combination_yield_detail_handler": [],
    "combination_dimensions": [],
}

# Each (req,resp) pair appended in EM APP order:
n = min(len(requests), len(responses))
for i in range(n):
    req = requests[i]
    resp = responses[i]
    if not req.get("body"):
        continue
    m = re.search(r'"method":"([^"]+)"', req["body"])
    z = re.search(r'"combinationId":"?(\d+)"?', req["body"])
    if not m:
        continue
    method = m.group(1)
    zid = z.group(1) if z else "?"
    if method in buckets:
        buckets[method].append({
            "zid": zid,
            "request_body": req["body"],
            "response_status": resp.get("status"),
            "response_body": resp.get("body_preview", ""),
        })

print("==PAIRS COLLECTED==")
for m, items in buckets.items():
    print(f"\n=== method={m} (n={len(items)}) ===")
    for it in items[:3]:
        print(f"  [zid={it['zid']}] status={it['response_status']}")
        print(f"  request_body: {it['request_body'][:1200]}")
        print(f"  response_body: {it['response_body'][:3000]}")
        print("  ----")