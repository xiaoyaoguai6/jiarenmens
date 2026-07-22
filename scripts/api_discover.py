"""Discover correct API parameters for player detail/position/trade."""
import requests
import json

API_URL = "https://emdcspzhapi.dfcfs.cn/rtV1"
zh_id = "900113132"
ua = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

s = requests.Session()
s.headers.update({"User-Agent": ua, "Referer": "https://groupwap.eastmoney.com"})

# Test rt_get_rank (known working)
params = {
    "type": "rt_get_rank",
    "rankType": "10005",
    "recIdx": 0,
    "recCnt": 5,
    "rankid": 0,
    "appVer": "9001000",
}
r = s.get(API_URL, params=params, timeout=30)
print("=== rt_get_rank (working) ===")
d = r.json()
print("result:", d.get("result"), ", data count:", len(d.get("data", [])))
if d.get("data"):
    for p in d["data"][:2]:
        print("  zjzh=", p.get("zjzh"), ", userid=", p.get("userid"))
print()

# Now try various types for getting player detail
types = [
    {"type": "rt_get_info", "zh": zh_id, "appVer": "9001000"},
    {"type": "rt_get_zjzh", "zjzh": zh_id, "appVer": "9001000"},
    {"type": "rt_get_zjzh_detail", "zjzh": zh_id, "appVer": "9001000"},
    {"type": "rt_get_userinfo", "zjzh": zh_id, "appVer": "9001000"},
    {"type": "rt_get_position", "zh": zh_id, "appVer": "9001000"},
    {"type": "rt_get_change", "zh": zh_id, "appVer": "9001000"},
    {"type": "rt_get_rank_detail", "zjzh": zh_id, "appVer": "9001000"},
    {"type": "rt_detail", "zjzh": zh_id, "appVer": "9001000"},
    {"type": "rt_info", "zjzh": zh_id, "appVer": "9001000"},
    {"type": "rt_zh_info", "zh": zh_id, "appVer": "9001000"},
    {"type": "rt_get_zh_detail", "zh": zh_id, "appVer": "9001000"},
    {"type": "get_zjzh_info", "zjzh": zh_id, "appVer": "9001000"},
    {"type": "get_info", "zh": zh_id, "appVer": "9001000"},
    {"type": "get_detail", "zh": zh_id, "appVer": "9001000"},
    {"type": "get_user_detail", "zh": zh_id, "appVer": "9001000"},
]

for params in types:
    query = {}
    for k, v in params.items():
        query[k] = v
    r = s.get(API_URL, params=query, timeout=30)
    try:
        d = r.json()
        msg = d.get("message", "")[:120]
        line = "type={:30s} | result={} | msg={}"
        print(line.format(params["type"], d.get("result"), msg))
    except Exception as e:
        line = "type={:30s} | parse error: {}"
        print(line.format(params["type"], r.text[:120]))

# Also try POST to apistock endpoint
print("\n=== api003 POST endpoint ===")
PROXY_URL = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson"

api003_tests = [
    {"path": "zuheV64/JS.aspx", "urlParm": {"zh": zh_id}},
    {"path": "zuheV64/JS.aspx", "urlParm": {"zjzh": zh_id}},
    {"path": "zuheV64/JS.aspx", "urlParm": {"type": "get_zjzh", "zjzh": zh_id}},
    {"path": "zuheV64/JS.aspx", "urlParm": {"type": "get_info", "zh": zh_id}},
    {"path": "zuheV64/JS.aspx", "urlParm": {"type": "get_detail", "zh": zh_id}},
    {"path": "zuheV64/JS.aspx", "urlParm": {"type": "get_position", "zh": zh_id}},
    {"path": "zuheV64/JS.aspx", "urlParm": {"type": "get_change", "zh": zh_id}},
]

for data in api003_tests:
    body = {}
    for k, v in data.items():
        body[k] = json.dumps(v) if isinstance(v, dict) else v
    r = s.post(
        PROXY_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    try:
        d = r.json()
        msg = d.get("message", "")[:120]
        line = "data={} | result={} | msg={}"
        print(line.format(
            json.dumps(data, ensure_ascii=False)[:100],
            d.get("result"),
            msg,
        ))
    except Exception as e:
        line = "data={} | error: {}"
        print(line.format(json.dumps(data, ensure_ascii=False)[:80], e))
