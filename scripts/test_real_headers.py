# -*- coding: utf-8 -*-
"""用真实APP的请求头测试API"""
import sys, io, json, requests, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 从Fiddler抓包中提取的真实APP请求头
REAL_APP_HEADERS = {
    "User-Agent": "okhttp/3.12.13",
    "EM-OS": "Android",
    "EM-PKG": "com.eastmoney.android.berlin",
    "EM-VER": "11.1.5",
    "EM-GT": "ceab-5fd3129d7a2df2bb6d1f258708cfb2af",
    "EM-MD": "M2MzMWU3MmM0OTBhMTZlYTFlODEyMmIwOTIzM2NjMDJ8fGllbWlfdGx1YWZlZF9tZQ%3D%3D",
    "EM-CHL": "nearme26_64",
    "EM-GV": "bd551d99c",
    "EM-SL": "0",
    "EM-PA": "1",
    "em-dns": "1",
}

# 也可以试试加上EM-CT和EM-UT（从Fiddler抓包中提取）
FULL_HEADERS = dict(REAL_APP_HEADERS)
FULL_HEADERS.update({
    "EM-CT": "BUhSbM2yS4BIobPWLfFikmmJfLL8IU8asaF1yDutQOmE6UkLyTwsFCvnJOfrbi_-nzo_r3PFxMcsRQ4Jmwa0L2ZmDk6NutUU2StjgHeKFTdDA7hY01qfvhWtggI0_2LU-fM-HwmSc85hNP8ahKL5UU7-Ay_TsTNHGQCP6IjMdaY",
    "EM-UT": "FobyicMgeV4Nr0is9gK0ARlq6I0wmmSdpxh5bQGH2RAtrem8rIqKWj8kG8g5-NMJJ3fxs-rgBFwkaTb1-MIVyP4abIFR5lLM9S6k6RUqXtvTVRhCGFbUjhWoXt_lHZSr6bD-HCImHyt8p6HZg0DbXgLI1XVINKO1UdUrc4xIABoWiF91Y5HWiPT699sx1clsQL8XS2pbzrQXC7KGImfgv8RgBcGxF7h5Pl9ZpPJobW_TfiD5DCCx1P5Jz9VN67obNWDbBekVIYZWPSaGShbXFk2kGcFeG45IPxWRXyMbMea7Xw3QMwLR2k2s08h6eq7Ryllk_DmZEKavisCRNhAWLG9N5FcILDRmsxAeg4WiOt0MQjQs9u0eebsXytIVfGIqLeWtRv3rMbY",
})

ZH = "900023658"

# 测试1: 用真实UA访问rtV1
print("=== 用真实APP UA 测试 rtV1 ===")
s = requests.Session()
s.headers.update(REAL_APP_HEADERS)

for api_type in ["rt_get_rank", "rt_get_info", "rt_get_position", "rt_get_change"]:
    params = {"type": api_type, "zh": ZH, "appVer": "9001000"}
    if api_type == "rt_get_rank":
        params.update({"rankType": "10004", "recIdx": "0", "recCnt": "3", "rankid": "0"})
    try:
        r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=10)
        d = r.json()
        result = d.get("result", "?")
        msg = d.get("message", "")[:60]
        print("  [%s] %s => result=%s msg=%s" % ("OK" if result == "0" else "FAIL", api_type, result, msg))
    except Exception as e:
        print("  [ERR] %s => %s" % (api_type, str(e)[:60]))

# 测试2: 用完整头测试
print("\n=== 用完整APP头(含EM-CT/EM-UT) 测试 ===")
s2 = requests.Session()
s2.headers.update(FULL_HEADERS)

for api_type in ["rt_get_rank", "rt_get_info", "rt_get_position", "rt_get_change"]:
    params = {"type": api_type, "zh": ZH, "appVer": "9001000"}
    if api_type == "rt_get_rank":
        params.update({"rankType": "10004", "recIdx": "0", "recCnt": "3", "rankid": "0"})
    try:
        r = s2.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=10)
        d = r.json()
        result = d.get("result", "?")
        msg = d.get("message", "")[:60]
        data = d.get("data")
        if result == "0" and data:
            if isinstance(data, list) and data:
                print("  [OK] %s => result=0 data_keys=%s" % (api_type, list(data[0].keys())[:10]))
            else:
                print("  [OK] %s => result=0 data=%s" % (api_type, str(data)[:100]))
        else:
            print("  [%s] %s => result=%s msg=%s" % ("OK" if result == "0" else "FAIL", api_type, result, msg))
    except Exception as e:
        print("  [ERR] %s => %s" % (api_type, str(e)[:60]))

# 测试3: POST请求
print("\n=== POST 请求 ===")
for api_type in ["rt_get_info", "rt_get_position", "rt_get_change"]:
    data = {"type": api_type, "zh": ZH, "appVer": "9001000"}
    try:
        r = s2.post("https://emdcspzhapi.dfcfs.cn/rtV1", data=data, timeout=10)
        print("  POST %s => [%d] %s" % (api_type, r.status_code, r.text[:100]))
    except Exception as e:
        print("  POST %s => ERR: %s" % (api_type, str(e)[:60]))

# 测试4: emstockdiag 网关 + 真实头
print("\n=== emstockdiag + 真实APP头 ===")
CID = "9f69c1bcff839a3202625794b00c75e3"
for path in [
    "v4/mobileadapter/gszcount",
    "v4/mobileadapter/positionlist",
    "v4/mobileadapter/tradelist",
    "v4/mobileadapter/detail",
    "rspThird/community/positionlist_handler",
    "rspThird/community/tradelist_handler",
]:
    body = {
        "path": path,
        "parm": json.dumps({"cid": CID, "zh": ZH}),
        "header": {"appkey": "a8157f5ef970edda2c103e192b6dc3e5", "Referer": "http://www.eastmoney.com"},
        "track": "sys_%d" % int(time.time() * 1000),
        "pageUrl": "https://groupwap.eastmoney.com/group/reality/info.html?zh=%s" % ZH,
    }
    try:
        r = s2.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData", json=body, timeout=10)
        d = r.json()
        rcode = d.get("RCode", "?")
        rdata = d.get("RData", "")
        if rdata:
            try:
                inner = json.loads(rdata)
                state = inner.get("state", "?")
                data = inner.get("data")
                if state == 0 and data:
                    print("  ** %s => state=0 data=%s" % (path, json.dumps(data, ensure_ascii=False)[:200]))
                elif state != -4:
                    print("     %s => state=%s msg=%s" % (path, state, inner.get("message", "")[:60]))
            except:
                print("     %s => RCode=%s RData=%s" % (path, rcode, str(rdata)[:100]))
        else:
            print("     %s => RCode=%s" % (path, rcode))
    except Exception as e:
        print("  [ERR] %s => %s" % (path, str(e)[:60]))
