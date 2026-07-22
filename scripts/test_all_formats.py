# -*- coding: utf-8 -*-
"""测试各种请求格式"""
import sys, io, json, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

ZH = "900113132"

# 1. GET rtV1 with all params
print("=== 1. GET rtV1 with all params ===")
params = {"type": "rt_get_info", "zh": ZH, "appVer": "9001000",
          "plat": "wap", "version": "101", "product": "emguba",
          "deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA"}
r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params, timeout=15)
print("  %s" % r.text[:200])

# 2. POST rtV1 with form data
print("\n=== 2. POST rtV1 form data ===")
r = s.post("https://emdcspzhapi.dfcfs.cn/rtV1", data=params, timeout=15)
print("  %s" % r.text[:200])

# 3. POST rtV1 with JSON body
print("\n=== 3. POST rtV1 JSON ===")
r = s.post("https://emdcspzhapi.dfcfs.cn/rtV1", json=params, timeout=15)
print("  %s" % r.text[:200])

# 4. POST /Tran/GetData with JSON (same format as page's AsyncRequestTran)
print("\n=== 4. POST /Tran/GetData ===")
body = {"url": "rtV1", "type": "rt_get_info",
        "data": {"zh": ZH, "appVer": "9001000"},
        "track": "sys_123", "pageUrl": "https://groupwap.eastmoney.com/"}
r = s.post("https://emdcspzhapi.dfcfs.cn/Tran/GetData", json=body, timeout=15)
print("  [%d] %s" % (r.status_code, r.text[:200]))

# 5. POST apistock/tran/getJson with rtV1 format
print("\n=== 5. POST apistock/tran/getJson ===")
r = s.post("https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson",
           data={"path": "rtV1", "pageUrl": "https://groupwap.eastmoney.com/",
                 "urlParm": json.dumps({"type": "rt_get_info", "zh": ZH, "appVer": "9001000"})},
           timeout=15)
print("  [%d] %s" % (r.status_code, r.text[:200]))

# 6. srtV1 endpoint
print("\n=== 6. GET srtV1 ===")
r = s.get("https://emdcspzhapi.dfcfs.cn/srtV1", params={"type": "rt_get_info", "zh": ZH, "appVer": "9001000"}, timeout=15)
print("  %s" % r.text[:200])

# 7. Try with zjzh instead of zh
print("\n=== 7. GET rtV1 with zjzh ===")
r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params={"type": "rt_get_info", "zjzh": ZH, "appVer": "9001000"}, timeout=15)
print("  %s" % r.text[:200])

# 8. Try emzuhelist
print("\n=== 8. emzuhelist ===")
r = s.get("https://emzuhelist.eastmoney.com/zuhe/api/Topic/GetInfo", params={"zh": ZH}, timeout=15)
print("  [%d] %s" % (r.status_code, r.text[:200]))
r = s.get("https://emzuhelist.eastmoney.com/zuhe/api/Topic/TopicList", params={"uid": "2012094520785316"}, timeout=15)
print("  [%d] %s" % (r.status_code, r.text[:200]))
