"""
Comprehensive API discovery script for East Money position data.
"""
import requests
import json

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://groupwap.eastmoney.com",
    "Accept": "application/json, text/plain, */*",
}
ZH = "900113132"
ZJZH = "900113132"

s = requests.Session()
s.headers.update(HEADERS)

results = []


def test(label, method, url, **kwargs):
    try:
        if method == "GET":
            r = s.get(url, timeout=15, **kwargs)
        else:
            r = s.post(url, timeout=15, **kwargs)
        try:
            data = r.json()
            result_val = data.get("result", "?")
            msg = data.get("message", "")[:80]
        except Exception:
            result_val = "HTTP %d" % r.status_code
            msg = r.text[:100]
        results.append((label, result_val, msg, len(r.text)))
        if result_val not in ("-10000", "?"):
            print("  *** HIT: %s -> result=%s, len=%d" % (label, result_val, len(r.text)))
            print("      msg=%s" % msg)
            print("      data=%s" % r.text[:500])
        else:
            print("  miss: %s -> result=%s" % (label, result_val))
    except Exception as e:
        results.append((label, "ERROR", str(e)[:100], 0))
        print("  err:  %s -> %s" % (label, str(e)[:100]))


def main():
    base = "https://emdcspzhapi.dfcfs.cn"

    # PART 1: zjzh parameter variations with rtV1
    print("\n" + "=" * 70)
    print("PART 1: zjzh parameter variations with rtV1")
    print("=" * 70)

    for ptype in ["rt_get_rank", "rt_get_info", "rt_get_position", "rt_get_change",
                   "rt_get_detail", "rt_get_holdings", "rt_get_stock_list",
                   "rt_get_player_info", "rt_get_player_position",
                   "rt_get_group_info", "rt_get_group_position",
                   "rt_get_zuhe_info", "rt_get_zuhe_position",
                   "rt_get_player_detail", "rt_get_player_change",
                   "rt_get_zuhe_detail", "rt_get_zuhe_change",
                   "rt_get_group_detail", "rt_get_group_change"]:
        test("rtV1 type=%s zjzh" % ptype,
             "GET", "%s/rtV1" % base,
             params={"type": ptype, "zjzh": ZJZH, "appVer": "9001000"})
        test("rtV1 type=%s zh+zjzh" % ptype,
             "GET", "%s/rtV1" % base,
             params={"type": ptype, "zh": ZH, "zjzh": ZJZH, "appVer": "9001000"})

    # PART 2: POST to rtV1
    print("\n" + "=" * 70)
    print("PART 2: POST to rtV1")
    print("=" * 70)

    for ptype in ["rt_get_info", "rt_get_position", "rt_get_change",
                   "rt_get_detail", "rt_get_holdings"]:
        test("rtV1 POST type=%s" % ptype,
             "POST", "%s/rtV1" % base,
             data={"type": ptype, "zh": ZH, "appVer": "9001000"})
        test("rtV1 POST-json type=%s" % ptype,
             "POST", "%s/rtV1" % base,
             json={"type": ptype, "zh": ZH, "appVer": "9001000"})

    # PART 3: srtV1 endpoint
    print("\n" + "=" * 70)
    print("PART 3: srtV1 endpoint")
    print("=" * 70)

    for ptype in ["rt_get_rank", "rt_get_info", "rt_get_position", "rt_get_change",
                   "rt_add_concern", "rt_cancel_concern",
                   "rt_get_concern_list", "rt_get_follower_list"]:
        test("srtV1 type=%s" % ptype,
             "GET", "%s/srtV1" % base,
             params={"type": ptype, "zh": ZH, "appVer": "9001000"})

    # PART 4: api003 POST
    print("\n" + "=" * 70)
    print("PART 4: api003 POST to apistock/tran/getJson")
    print("=" * 70)

    api003_url = "%s/apistock/tran/getJson" % base
    page_url = "https://groupwap.eastmoney.com/group/reality/info.html"

    for urlParm in [
        "type=rt_get_info&zh=%s&appVer=9001000" % ZH,
        "type=rt_get_position&zh=%s&appVer=9001000" % ZH,
        "type=rt_get_change&zh=%s&appVer=9001000" % ZH,
    ]:
        test("api003 zuheV64 parm=%s" % urlParm[:50],
             "POST", api003_url,
             data={"path": "zuheV64/JS.aspx", "pageUrl": page_url, "urlParm": urlParm})

    parm_list = json.dumps([
        {"deviceid": "DCB485C9C5E69EC1543FC90B84C6EBFA"},
        {"plat": "wap"}, {"product": "guba"}, {"version": "101"}, {"id": ZH}
    ])
    for path in [
        "zuhe/api/Shipan/GetInfo",
        "zuhe/api/Shipan/GetPosition",
        "zuhe/api/Shipan/GetChange",
        "zuhe/api/Shipan/GetDetail",
        "zuheV64/ShipanInfo.aspx",
        "zuheV64/ShipanPosition.aspx",
        "zuheV64/ShipanChange.aspx",
        "zuheV64/ShipanDetail.aspx",
    ]:
        test("api003 path=%s" % path,
             "POST", api003_url,
             data={"path": path, "pageUrl": page_url, "parm": parm_list})

    # PART 5: Different API endpoints
    print("\n" + "=" * 70)
    print("PART 5: Different API endpoints")
    print("=" * 70)

    test("datacenter RPT_REAL_COMBOSTOCK",
         "GET", "https://datacenter-web.eastmoney.com/api/data/v1/get",
         params={"reportName": "RPT_REAL_COMBOSTOCK", "columns": "ALL",
                 "filter": '(COMBO_ID="%s")' % ZH, "pageNumber": "1", "pageSize": "50"})
    test("datacenter RPT_REAL_PLAYER",
         "GET", "https://datacenter-web.eastmoney.com/api/data/v1/get",
         params={"reportName": "RPT_REAL_PLAYER", "columns": "ALL",
                 "filter": '(COMBO_ID="%s")' % ZH, "pageNumber": "1", "pageSize": "50"})

    # PART 6: Examine full rank API response
    print("\n" + "=" * 70)
    print("PART 6: Examine rank API response structure")
    print("=" * 70)

    r = s.get("%s/rtV1" % base,
              params={"type": "rt_get_rank", "rankType": "10004",
                      "recIdx": 0, "recCnt": 2, "rankid": 0, "appVer": "9001000"},
              timeout=15)
    data = r.json()
    print("  Keys: %s" % list(data.keys()) if isinstance(data, dict) else "not dict")
    if isinstance(data, dict) and "data" in data:
        d = data["data"]
        if isinstance(d, list) and len(d) > 0:
            player = d[0]
            print("  Player keys: %s" % list(player.keys()))
            print("  Full: %s" % json.dumps(player, ensure_ascii=False)[:800])

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: Non -10000 results")
    print("=" * 70)
    for label, result, msg, length in results:
        if result not in ("-10000", "?"):
            print("  *** %s: result=%s, msg=%s, len=%d" % (label, result, msg[:80], length))
    print("\nTotal tests: %d, Non-failures: %d" % (len(results),
         sum(1 for _, r, _, _ in results if r not in ("-10000", "?"))))


if __name__ == "__main__":
    main()
