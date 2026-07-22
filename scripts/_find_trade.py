import requests, json
base = "https://spzhapi.eastmoney.com/rtV1"
headers = {"User-Agent":"okhttp/3.12.13","Host":"spzhapi.eastmoney.com"}
# replay change endpoint exactly as captured
r = requests.get(base, params={
    "reqUserid":"8295376072559048",
    "recIdx":"1",
    "type":"rt_hold_change72",
    "recCnt":"10",
    "zh":"900235873",
}, headers=headers, timeout=15)
print("status", r.status_code, "len", len(r.text))
j = r.json()
print("result:", j.get("result"), "msg:", j.get("message"), "listSize:", j.get("listSize"))
d = j.get("data") or []
print("n_rows:", len(d))
print("sample keys:", list(d[0].keys()) if d else "(empty)")
for row in d[:5]:
    print(" ", json.dumps(row, ensure_ascii=False))

# test 2: does reqUserid matter?
print()
print("--- no reqUserid ---")
r2 = requests.get(base, params={"type":"rt_hold_change72","recIdx":"1","recCnt":"10","zh":"900235873"}, headers=headers, timeout=15)
j2 = r2.json()
print("result:", j2.get("result"), "listSize:", j2.get("listSize"), "n:", len(j2.get("data") or []))

# test 3: other zhid
print()
print("--- zh=900083077 ---")
r3 = requests.get(base, params={"type":"rt_hold_change72","recIdx":"1","recCnt":"10","zh":"900083077"}, headers=headers, timeout=15)
j3 = r3.json()
print("result:", j3.get("result"), "listSize:", j3.get("listSize"), "n:", len(j3.get("data") or []))
for row in (j3.get("data") or [])[:3]:
    print(" ", json.dumps(row, ensure_ascii=False))

# test 4: paginate (recIdx=2,11 etc) and big recCnt
print()
print("--- recIdx=11 recCnt=50 ---")
r4 = requests.get(base, params={"type":"rt_hold_change72","recIdx":"11","recCnt":"50","zh":"900235873"}, headers=headers, timeout=15)
j4 = r4.json()
print("result:", j4.get("result"), "listSize:", j4.get("listSize"), "n:", len(j4.get("data") or []))