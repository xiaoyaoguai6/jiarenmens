import json
from pathlib import Path
p = Path(r'D:\project\jiarenmens\data\recon\em.flows')
methods_to_keep = ['CombinationHoldPositionPermitHandler','CombinationHoldBlockPermitHandler','CombinationRelocatePositionHandler','CombinationInfoHandler','combination_yield_detail_handler','combination_dimensions']
buckets = {m:[] for m in methods_to_keep}
for line in p.read_text(encoding='utf-8').splitlines():
    try:
        rec = json.loads(line)
    except Exception: continue
    if rec.get('host') != 'spzhapi.dfcfs.cn': continue
    if rec.get('phase') != 'response': continue
    # find matched method via pairing - cannot easily without index; use timestamp lookup against request log entries encountered earlier
# Re-read paired: maintain dict ts -> method
req_by_ts = {}
for line in p.read_text(encoding='utf-8').splitlines():
    try: rec = json.loads(line)
    except: continue
    if rec.get('host') != 'spzhapi.dfcfs.cn': continue
    if rec.get('phase') == 'request' and rec.get('body'):
        import re
        mm = re.search(r'\"method\":\"([^\"]+)\"', rec['body'])
        z = re.search(r'\"combinationId\":\"?(\d+)\"?', rec['body'])
        method = mm.group(1) if mm else '?'
        zid = z.group(1) if z else '?'
        req_by_ts[round(rec['ts'],3)] = (method, zid)
# Now match responses within 5s of any request
for line in p.read_text(encoding='utf-8').splitlines():
    try: rec = json.loads(line)
    except: continue
    if rec.get('host') != 'spzhapi.dfcfs.cn': continue
    if rec.get('phase') != 'response': continue
    # match request by ts within +/- 3s
    candidates = [(abs(ts-rec['ts']),m,z) for ts,(m,z) in req_by_ts.items() if abs(ts-rec['ts'])<3]
    if not candidates: continue
    candidates.sort()
    method, zid = candidates[0][1], candidates[0][2]
    if method in buckets:
        buckets[method].append({'zid':zid, 'status':rec.get('status'),'body':rec.get('body_preview','')})

for m, items in buckets.items():
    print(f'=== {m}: {len(items)} response(s) ===')
    for it in items[:2]:
        print(f'  [zid={it[\"zid\"]}] status={it[\"status\"]}')
        print(f'  body: {it[\"body\"][:1500]}')
        print('  ---')
