import json, sys, requests, uuid, time
sys.path.insert(0, r"D:\project\jiarenmens")
from scripts.polldirect import _post_detail, load_em_headers, map_positions, map_trades

zh = "900235873"
payload = _post_detail(zh)

print("=== combination_detail_97 顶层 keys ===")
print(list(payload.keys()))
print()

print("=== detail 选手画像 (核心指标) ===")
d = payload.get("detail", {})
keep = ["zuheName","uidNick","zjzh","comment","uidComment",
        "JZ","rate","rateDay","rate5Day","rate20Day","rate60Day","rate250Day",
        "maxDrawDown","yxts","dealWinCnt","dealfailCnt","dealRate",
        "rateMaxStk","rateMaxStkName","concernCnt","startDate","userid"]
for k in keep:
    if k in d: print(f"  {k:18s} = {d[k]!r:.80}")
print()

print("=== position[] 持仓明细 (每只股票一行) ===")
pos_rows = payload.get("position", []) or []
print(f"n_rows = {len(pos_rows)}")
print("字段名:", list(pos_rows[0].keys()) if pos_rows else "(empty)")
for p in pos_rows[:5]:
    print(f"  {p.get('__code')} {p.get('__name')} cbj={p.get('cbj')} zxjg={p.get('__zxjg')} yk={p.get('webYkRate')}% pos={p.get('holdPos')}% mkt={p.get('stkMktCode')}")
print()

print("=== tradeSummary[] 调仓明细 (每条调仓一行) ===")
trd_rows = payload.get("tradeSummary", []) or []
print(f"n_rows = {len(trd_rows)}")
print("字段名:", list(trd_rows[0].keys()) if trd_rows else "(empty)")
for t in trd_rows[:5]:
    print(f"  {t.get('tzrq')} {t.get('stkMktCode')}{t.get('stkName')} 买={t.get('lshj_mr')}档={t.get('cwhj_mr')}价={t.get('cjjg_mr')} | 卖={t.get('lshj_mc')}档={t.get('cwhj_mc')}价={t.get('cjjg_mc')}")