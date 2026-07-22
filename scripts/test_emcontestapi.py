# -*- coding: utf-8 -*-
"""测试emcontestapi.eastmoney.com的所有可能端点"""
import sys, io, json, requests, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 真实APP请求头
HEADERS = {
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

s = requests.Session()
s.headers.update(HEADERS)

ZH = "900023658"
BASE = "https://emcontestapi.eastmoney.com"

# 测试各种路径和方法
tests = [
    # GET 请求
    ("GET", "/rtV1", {"type": "rt_get_rank", "rankType": "10004", "recIdx": "0", "recCnt": "3", "rankid": "0", "appVer": "9001000"}),
    ("GET", "/rtV1", {"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}),
    ("GET", "/rtV1", {"type": "rt_get_position", "zh": ZH, "appVer": "9001000"}),
    ("GET", "/rtV1", {"type": "rt_get_change", "zh": ZH, "appVer": "9001000"}),
    ("GET", "/rtV1", {"type": "rt_zhuhe_yk_new", "zh": ZH, "recIdx": "0", "recCnt": "100", "ykType": "20", "indexCode": "000300", "appVer": "9001000"}),
    ("GET", "/srtV1", {"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}),
    ("GET", "/srtV1", {"type": "rt_get_position", "zh": ZH, "appVer": "9001000"}),
    ("GET", "/msgcenter/my/getallbadges", {"uid": "8953027422282872", "ver": "11.1.5"}),
    # POST 请求
    ("POST", "/rtV1", {"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}),
    ("POST", "/rtV1", {"type": "rt_get_position", "zh": ZH, "appVer": "9001000"}),
    ("POST", "/Tran/GetData", {"url": "rtV1", "type": "rt_get_info", "data": {"zh": ZH, "appVer": "9001000"}}),
    ("POST", "/apistock/Tran/GetData", {"path": "v4/mobileadapter/gszcount", "parm": json.dumps({"cid": "9f69c1bcff839a3202625794b00c75e3"})}),
    # 其他路径
    ("GET", "/zuhe/api/Topic/GetInfo", {"zh": ZH}),
    ("GET", "/zuhe/api/Topic/TopicList", {"uid": "2012094520785316"}),
    ("GET", "/api/v1/position", {"zh": ZH}),
    ("GET", "/api/v1/detail", {"zh": ZH}),
    ("GET", "/rspThird/community/positionlist_handler", {"zh": ZH}),
    ("GET", "/rspThird/community/detail_handler", {"zh": ZH}),
    ("GET", "/v4/mobileadapter/gszcount", {"cid": "9f69c1bcff839a3202625794b00c75e3"}),
    ("GET", "/v4/mobileadapter/positionlist", {"cid": "9f69c1bcff839a3202625794b00c75e3", "zh": ZH}),
    ("GET", "/msgcenter/my/getallbadges", {"uid": "8953027422282872", "ver": "11.1.5", "ext": "6ec675207d43851ddb9fbbc21ac48c65"}),
]

print("=== emcontestapi.eastmoney.com 测试 ===\n")
for method, path, params in tests:
    url = BASE + path
    try:
        if method == "GET":
            r = s.get(url, params=params, timeout=10)
        else:
            r = s.post(url, json=params, timeout=10)
        body = r.text[:200]
        try:
            d = json.loads(body)
            result = d.get("result", d.get("status", d.get("RCode", d.get("code", "?"))))
            msg = str(d.get("message", d.get("msg", d.get("error", ""))))[:60]
            print("  [%d] %s %s => %s %s" % (r.status_code, method, path, result, msg))
            # 如果有数据，显示详情
            data = d.get("data", d.get("RData"))
            if data and isinstance(data, list) and data:
                print("       data: list[%d] keys=%s" % (len(data), list(data[0].keys())[:10]))
            elif data and isinstance(data, dict) and data:
                print("       data: keys=%s" % list(data.keys())[:10])
        except:
            if "html" in r.headers.get("content-type", "").lower():
                print("  [%d] %s %s => HTML页面" % (r.status_code, method, path))
            else:
                print("  [%d] %s %s => %s" % (r.status_code, method, path, body[:80]))
    except Exception as e:
        print("  [ERR] %s %s => %s" % (method, path, str(e)[:60]))

# 也测试几个可能的子域名
print("\n=== 其他可能的子域名 ===")
subdomains = [
    "emcontestapi.eastmoney.com",
    "emcontest.eastmoney.com",
    "contestapi.eastmoney.com",
    "emshipanapi.eastmoney.com",
    "emshipan.eastmoney.com",
    "shipan.eastmoney.com",
    "emcombo.eastmoney.com",
    "comboapi.eastmoney.com",
]
for domain in subdomains:
    url = "https://%s/rtV1" % domain
    try:
        r = s.get(url, params={"type": "rt_get_rank", "rankType": "10004", "recIdx": "0", "recCnt": "1", "rankid": "0", "appVer": "9001000"}, timeout=8)
        body = r.text[:100]
        try:
            d = json.loads(body)
            result = d.get("result", d.get("status", "?"))
        except:
            result = "HTML"
        print("  [%d] %s => %s" % (r.status_code, domain, result))
    except Exception as e:
        print("  [ERR] %s => %s" % (domain, str(e)[:60]))
