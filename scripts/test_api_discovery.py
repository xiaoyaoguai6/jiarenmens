"""
Discover working APIs for East Money position data.
Test multiple API endpoints and parameter combinations.
"""
import requests
import json

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)
REFERER = "https://groupwap.eastmoney.com"

session = requests.Session()
session.headers.update({"User-Agent": UA, "Referer": REFERER})

ZH_ID = "900113132"
API_URL = "https://emdcspzhapi.dfcfs.cn/rtV1"


def test_api(label, params):
    try:
        r = session.get(API_URL, params=params, timeout=10)
        d = r.json()
        result_code = d.get("result", "?")
        raw = d.get("data", "")
        has_data = raw is not None and raw != "" and raw != []
        if isinstance(raw, list) and raw:
            preview = json.dumps(raw[0], ensure_ascii=False)[:300]
        elif isinstance(raw, str):
            preview = raw[:300]
        else:
            preview = str(raw)[:300]
        print(f"  {label:40s} result={result_code}  data_len={len(str(raw))}  preview={preview}")
    except Exception as e:
        print(f"  {label:40s} ERROR: {e}")


def main():
    print("=" * 80)
    print("Phase 1: Test known API types with variations")
    print("=" * 80)

    test_api("rt_get_rank (basic)", {
        "type": "rt_get_rank", "rankType": "10004",
        "recIdx": 0, "recCnt": 1, "rankid": 0, "appVer": "9001000"
    })

    test_api("rt_get_rank + zh param", {
        "type": "rt_get_rank", "rankType": "10004",
        "recIdx": 0, "recCnt": 1, "rankid": 0, "appVer": "9001000",
        "zh": ZH_ID
    })

    detail_types = [
        "rt_get_info", "rt_get_position", "rt_get_change", "rt_get_detail",
        "rt_get_userinfo", "rt_get_stock", "rt_get_hold", "rt_get_holding",
        "rt_get_position_list", "rt_get_portfolio", "rt_get_trade",
        "rt_get_trade_list", "rt_get_position_detail", "rt_get_summary",
        "rt_get_overview", "rt_get_fund", "rt_get_asset",
        "rt_get_history", "rt_get_record", "rt_get_rebalance",
        "rt_get_stock_list", "rt_get_zjzh", "rt_get_combodetail",
    ]
    for t in detail_types:
        test_api(t, {"type": t, "zh": ZH_ID, "appVer": "9001000"})

    print()
    print("=" * 80)
    print("Phase 2: Test with additional common APP params")
    print("=" * 80)

    extra_params = {
        "zh": ZH_ID, "appVer": "9001000",
        "DeviceId": "DCB485C9C5E69EC1543FC90B84C6EBFA",
        "OS": "2",
        "AppName": "东方财富",
    }
    for t in ["rt_get_info", "rt_get_position", "rt_get_change", "rt_get_detail"]:
        params = {"type": t}
        params.update(extra_params)
        test_api(f"{t} (full params)", params)

    print()
    print("=" * 80)
    print("Phase 3: Test api003 endpoint")
    print("=" * 80)

    api003_url = "https://emdcspzhapi.dfcfs.cn/apistock/tran/getJson"
    for path in ["zuheV64/JS.aspx", "zuheV64/getPosition.aspx", "zuheV64/getDetail.aspx"]:
        for key in ["zh", "zjzh"]:
            try:
                payload = {"path": path, "pageUrl": REFERER, key: ZH_ID}
                r = session.post(api003_url, data=payload, timeout=10)
                print(f"  api003 {path} + {key}: status={r.status_code} len={len(r.text)} preview={r.text[:200]}")
            except Exception as e:
                print(f"  api003 {path} + {key}: ERROR {e}")

    print()
    print("=" * 80)
    print("Phase 4: Test other East Money domains")
    print("=" * 80)

    other_apis = [
        ("https://push2.eastmoney.com/api/qt/stock/get", {
            "secid": "0.000001", "fields1": "f1,f2,f3", "fields2": "f51,f52,f53"
        }),
        ("https://datacenter-web.eastmoney.com/api/data/v1/get", {
            "reportName": "RPT_PORTFOLIO_POSITION",
            "columns": "ALL",
            "filter": f'(ZJZH="{ZH_ID}")',
        }),
    ]
    for url, params in other_apis:
        try:
            r = session.get(url, params=params, timeout=10)
            print(f"  {url[:60]}: status={r.status_code} len={len(r.text)} preview={r.text[:200]}")
        except Exception as e:
            print(f"  {url[:60]}: ERROR {e}")


if __name__ == "__main__":
    main()
