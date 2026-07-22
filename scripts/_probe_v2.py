import requests, json, uuid, time
BASE = "https://emdcspzhapi.eastmoney.com/rtV2"
H = {
    "Content-Type":"application/json; charset=UTF-8",
    "EM-CHL":"taobao45","EM-CT":"",
    "EM-GT":"cean-cce6b56eac83e024ef690e55d3bf23ce","EM-GV":"c82971043",
    "EM-MD":"YjUyMTZhY2UzZGE4MGYxY2MzYzQ4ODVmNTQwYzdkN2F8fDM0NTgxODQyMDMyNTg1Mw==",
    "EM-OS":"Android","EM-PA":"1","EM-PKG":"com.eastmoney.android.newyork",
    "EM-SL":"0","EM-UT":"","EM-VER":"10.13.5",
    "Host":"emdcspzhapi.eastmoney.com","User-Agent":"okhttp/3.12.13",
}
def call(method, zh="900235873", extra=None):
    body = {"args":{"reqUserid":"","zh":zh, **(extra or {})},
            "clientType":"cfzq","method":method,
            "client":"android","appKey":"eastmoney","clientVersion":"10.13.5",
            "randomCode":str(uuid.uuid4()),"timestamp":int(time.time()*1000)}
    return requests.post(BASE, json=body, headers=H, timeout=15)

# 1. 看 tradeSummary 完整内容
print("=== combination_detail_97 -> tradeSummary ===")
r = call("combination_detail_97")
j = r.json()
ts = j["data"].get("tradeSummary")
print("tradeSummary type:", type(ts).__name__)
if ts is not None:
    print(json.dumps(ts, ensure_ascii=False, indent=2)[:2500])

# 2. position header
print()
print("=== position sample (first 3 rows) ===")
for p in j["data"]["position"][:3]:
    print(" ", json.dumps(p, ensure_ascii=False))

# 3. try combination_dimensions with unit variants
print()
for unit in ["1","5","20","60","day","week","month","all","d","w","m","q","y"]:
    r = call("combination_dimensions", extra={"unit":unit})
    j = r.json()
    tmp = j.get("message","")
    data = j.get("data")
    info = ""
    if isinstance(data, dict): info = "keys="+",".join(list(data.keys())[:5])
    elif isinstance(data, list): info = f"len={len(data)}"
    print(f"  unit={unit:5s} msg={tmp!r:.30} data_info={info}")