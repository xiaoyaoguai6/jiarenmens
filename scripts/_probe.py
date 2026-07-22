import requests, json
BASE = "https://spzhapi.eastmoney.com/rtV1"

# A: 用户最初抓到的完整 EM 头
FULL = {
    "Accept-Encoding": "gzip",
    "EM-CHL": "taobao45",
    "EM-CT": "",
    "EM-GT": "cean-cce6b56eac83e024ef690e55d3bf23ce",
    "EM-GV": "c82971043",
    "EM-MD": "YjUyMTZhY2UzZGE4MGYxY2MzYzQ4ODVmNTQwYzdkN2F8fDM0NTgxODQyMDMyNTg1Mw==",
    "EM-OS": "Android",
    "EM-PA": "1",
    "EM-PKG": "com.eastmoney.android.newyork",
    "EM-SL": "0",
    "EM-UT": "",
    "EM-VER": "10.13.5",
    "Host": "spzhapi.eastmoney.com",
    "User-Agent": "okhttp/3.12.13",
}

for label, hdrs in [("full_em_headers", FULL), ("min_ua_only", {"User-Agent":"okhttp/3.12.13","Host":"spzhapi.eastmoney.com"})]:
    print(f"=== {label} ===")
    r = requests.get(BASE, params={"appVer":"10013005","type":"rt_hold_detail86","zh":"900235873"}, headers=hdrs, timeout=15)
    print("  status:", r.status_code, "len:", len(r.text))
    try:
        j = r.json()
        print("  result:", j.get("result"), "msg:", j.get("message"), "listSize:", j.get("listSize"))
    except Exception as e:
        print("  not-JSON:", r.text[:200])