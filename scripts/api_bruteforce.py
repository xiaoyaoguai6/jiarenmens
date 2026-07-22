"""Brute force API parameter discovery."""
import requests, json
from urllib.parse import urlencode

zh = "900113132"
s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0",
    "Referer": "https://groupwap.eastmoney.com",
    "Origin": "https://groupwap.eastmoney.com",
})

# 1. POST to rtV1 with form body
print("=== POST to rtV1 ===")
bodies = [
    {"type": "rt_get_info", "zh": zh, "appVer": "9001000"},
    {"type": "rt_get_info", "zjzh": zh, "appVer": "9001000"},
    {"type": "rt_get_info", "userid": zh, "appVer": "9001000"},
]
for body in bodies:
    r = s.post("https://emdcspzhapi.dfcfs.cn/rtV1", data=body, timeout=30)
    try:
        d = r.json()
        print(f"POST {body} => {d.get('result')} {d.get('message','')[:80]}")
    except:
        print(f"POST {body} => {r.text[:120]}")

# 2. Try different appVer values
print("\n=== Different appVer ===")
for ver in ["9001000", "11001000", "12001000", "13001000", "10.0.0", "12.0.0", "13.0.0", "13.5.0"]:
    params = {"type": "rt_get_rank", "rankType": "10005", "recIdx": 0, "recCnt": 1, "rankid": 0, "appVer": ver}
    r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=30)
    d = r.json()
    ok = d.get("result") == "0"
    print(f"appVer={ver:12s} => result={d.get('result')} {'OK' if ok else 'FAIL'}")

# 3. Try rank data with recCnt=1 to see all fields
print("\n=== Rank data fields ===")
params = {"type": "rt_get_rank", "rankType": "10004", "recIdx": 0, "recCnt": 1, "rankid": 0, "appVer": "9001000"}
r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=30)
d = r.json()
if d.get("data"):
    p = d["data"][0]
    print("Rank player fields:", json.dumps(p, ensure_ascii=False, indent=2))

# 4. Try api003 with proper multipart/form-data
print("\n=== api003 with different content types ===")
for ct in ["application/x-www-form-urlencoded", "application/json; charset=UTF-8"]:
    data = {"path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html", "urlParm": json.dumps({"zh": zh})}
    if "json" in ct:
        r = s.post("https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson", json=data, timeout=30)
    else:
        r = s.post("https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson", data=data, timeout=30)
    try:
        d = r.json()
        print(f"CT={ct}: result={d.get('result')} msg={d.get('message','')[:80]}")
    except:
        print(f"CT={ct}: {r.text[:120]}")

# 5. Try api003 to emstockdiag
print("\n=== api003 to emstockdiag ===")
data = {"path": "zuheV64/JS.aspx", "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html", "urlParm": json.dumps({"zh": zh})}
r = s.post("https://emstockdiag.eastmoney.com/apistock/tran/getJson", data=data, timeout=30)
try:
    d = r.json()
    print(f"emstockdiag: result={d.get('result')} msg={d.get('message','')[:80]}")
except:
    print(f"emstockdiag: {r.text[:120]}")
