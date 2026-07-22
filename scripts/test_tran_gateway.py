# -*- coding: utf-8 -*-
"""测试 emstockdiag.eastmoney.com/Tran/GetData 网关"""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import requests

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

# 模拟 AsyncRequestTran.api001 的 POST 数据格式
post_body = {
    "url": "rtV1",
    "type": "rt_get_rank",
    "data": {"rankType": "10004", "recIdx": "0", "recCnt": "3", "rankid": "0", "appVer": "9001000"},
    "track": "sys_1234567890",
    "pageUrl": "https://groupwap.eastmoney.com/group/reality/detail.html?zh=900113132",
}

# 测试 emstockdiag
print("=== emstockdiag.eastmoney.com/Tran/GetData ===")
try:
    r = s.post("https://emstockdiag.eastmoney.com/Tran/GetData", json=post_body, timeout=15)
    print("Status: %d" % r.status_code)
    print("Body: %s" % r.text[:500])
except Exception as e:
    print("Error: %s" % e)

# 测试 emdcspzhapi
print("\n=== emdcspzhapi.dfcfs.cn/Tran/GetData ===")
try:
    r = s.post("https://emdcspzhapi.dfcfs.cn/Tran/GetData", json=post_body, timeout=15)
    print("Status: %d" % r.status_code)
    print("Body: %s" % r.text[:500])
except Exception as e:
    print("Error: %s" % e)

# 测试 empts.eastmoney.com
print("\n=== empts.eastmoney.com/Tran/GetData ===")
try:
    r = s.post("https://empts.eastmoney.com/Tran/GetData", json=post_body, timeout=15)
    print("Status: %d" % r.status_code)
    print("Body: %s" % r.text[:500])
except Exception as e:
    print("Error: %s" % e)

# 测试 emstockdiag with apistock path (之前测试过的格式)
print("\n=== emstockdiag apistock/Tran/GetData ===")
body2 = {
    "path": "v4/mobileadapter/gszcount",
    "parm": json.dumps({"cid": "test"}),
    "header": {"appkey": "a8157f5ef970edda2c103e192b6dc3e5", "Referer": "http://www.eastmoney.com"},
    "track": "sys_1234567890",
    "pageUrl": "https://emcreative.eastmoney.com/app_fortune/person/index.html",
}
try:
    r = s.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData", json=body2, timeout=15)
    print("Status: %d" % r.status_code)
    d = r.json()
    print("RCode: %s RData: %s" % (d.get("RCode"), str(d.get("RData", ""))[:200]))
except Exception as e:
    print("Error: %s" % e)
