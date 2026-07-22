# -*- coding: utf-8 -*-
"""
分析抓包数据，提取 API 请求模式

读取 data/captured/ 目录下的 JSON 文件，
分析请求参数、响应格式，生成可复现的 Python 代码。
"""
import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from collections import Counter

CAPTURE_DIR = Path(r"D:\project\jiarenmens\data\captured")


def load_captures():
    """加载所有捕获数据"""
    captures = []
    if not CAPTURE_DIR.exists():
        print("捕获目录不存在: %s" % CAPTURE_DIR)
        return captures

    for f in sorted(CAPTURE_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                data["_file"] = f.name
                captures.append(data)
        except Exception as e:
            print("  加载失败 %s: %s" % (f.name, e))

    return captures


def analyze_captures(captures):
    """分析捕获数据"""
    if not captures:
        print("没有捕获数据")
        return

    print("=" * 60)
    print("抓包数据分析")
    print("=" * 60)
    print("总请求数: %d" % len(captures))

    # 按域名分组
    domain_counts = Counter(c.get("domain", "?") for c in captures)
    print("\n按域名统计:")
    for domain, count in domain_counts.most_common():
        print("  %s: %d 次" % (domain, count))

    # 按路径分组
    path_counts = Counter(c.get("path", "?") for c in captures)
    print("\n按路径统计:")
    for path, count in path_counts.most_common(20):
        print("  %s: %d 次" % (path, count))

    # 分析 API 请求
    print("\n" + "=" * 60)
    print("API 请求详情")
    print("=" * 60)

    for c in captures:
        domain = c.get("domain", "")
        path = c.get("path", "")
        method = c.get("method", "")
        status = c.get("response_status", 0)

        # 只关注 API 请求
        if not any(k in domain for k in ["emdcspzhapi", "emstockdiag", "spzhapi"]):
            if not any(k in path for k in ["api", "rtV1", "Tran", "GetData"]):
                continue

        print("\n--- %s %s%s [%d] ---" % (method, domain, path, status))
        print("  时间: %s" % c.get("timestamp", ""))

        # 请求参数
        query = c.get("query", "")
        if query:
            print("  Query: %s" % query[:300])

        req_body = c.get("request_body", "")
        if req_body:
            print("  Request Body: %s" % req_body[:300])

        # 响应
        resp_body = c.get("response_body", "")
        if resp_body:
            try:
                d = json.loads(resp_body)
                result = d.get("result", d.get("RCode", "?"))
                msg = d.get("message", d.get("RData", ""))[:100]
                print("  Response: result=%s msg=%s" % (result, msg))

                # 如果有数据，显示结构
                data = d.get("data", d.get("RData"))
                if data:
                    if isinstance(data, list) and data:
                        print("  Data: list[%d] keys=%s" % (len(data), list(data[0].keys())[:10]))
                    elif isinstance(data, str):
                        try:
                            inner = json.loads(data)
                            if isinstance(inner, dict):
                                print("  RData: state=%s data_keys=%s" % (inner.get("state"), list(inner.get("data", {}).keys()) if isinstance(inner.get("data"), dict) else "?"))
                        except:
                            print("  RData: %s" % data[:200])
                    elif isinstance(data, dict):
                        print("  Data: keys=%s" % list(data.keys())[:10])
            except:
                print("  Response: %s" % resp_body[:200])

    # 提取可复现的请求
    print("\n" + "=" * 60)
    print("可复现的 API 请求 (Python 代码)")
    print("=" * 60)

    for c in captures:
        domain = c.get("domain", "")
        path = c.get("path", "")
        method = c.get("method", "")
        status = c.get("response_status", 0)

        if status != 200:
            continue

        if not any(k in domain for k in ["emdcspzhapi", "emstockdiag", "spzhapi"]):
            continue

        url = c.get("url", "")
        query = c.get("query", "")
        req_body = c.get("request_body", "")
        req_headers = c.get("request_headers", {})

        print("\n# %s%s" % (domain, path))
        print("# 状态: %d  时间: %s" % (status, c.get("timestamp", "")))

        if method == "GET" and query:
            params = parse_qs(query, keep_blank_values=True)
            params_flat = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            print("params = %s" % json.dumps(params_flat, ensure_ascii=False, indent=4))
            print("r = s.get('%s', params=params, timeout=15)" % url.split("?")[0])
        elif method == "POST":
            if req_body:
                try:
                    body = json.loads(req_body)
                    print("body = %s" % json.dumps(body, ensure_ascii=False, indent=4))
                    print("r = s.post('%s', json=body, timeout=15)" % url)
                except:
                    print("body = %s" % repr(req_body[:200]))
                    print("r = s.post('%s', data=body, timeout=15)" % url)

        resp_body = c.get("response_body", "")
        try:
            d = json.loads(resp_body)
            if d.get("result") == "0" or d.get("RCode") == 200:
                print("# 成功! 响应: %s" % resp_body[:200])
        except:
            pass


def generate_scraper(captures):
    """根据抓包数据生成爬虫代码"""
    print("\n" + "=" * 60)
    print("生成的爬虫代码")
    print("=" * 60)

    # 找到成功的 API 请求
    working_apis = []
    for c in captures:
        status = c.get("response_status", 0)
        if status != 200:
            continue
        domain = c.get("domain", "")
        if not any(k in domain for k in ["emdcspzhapi", "emstockdiag", "spzhapi"]):
            continue
        resp_body = c.get("response_body", "")
        try:
            d = json.loads(resp_body)
            if d.get("result") == "0" or d.get("RCode") == 200:
                working_apis.append(c)
        except:
            pass

    if not working_apis:
        print("# 没有找到成功的 API 请求")
        return

    print("""
import requests, json

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://groupwap.eastmoney.com"})

""")

    for i, c in enumerate(working_apis):
        url = c.get("url", "").split("?")[0]
        method = c.get("method", "")
        query = c.get("query", "")
        req_body = c.get("request_body", "")
        path = c.get("path", "")

        print("# API %d: %s%s" % (i + 1, c.get("domain", ""), path))

        if method == "GET" and query:
            params = parse_qs(query, keep_blank_values=True)
            params_flat = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            print("def api_%d(zh_id):" % (i + 1))
            print("    params = %s" % json.dumps(params_flat, ensure_ascii=False))
            print("    params['zh'] = zh_id")
            print("    r = s.get('%s', params=params, timeout=15)" % url)
            print("    return r.json()")
        elif method == "POST" and req_body:
            try:
                body = json.loads(req_body)
                print("def api_%d(zh_id):" % (i + 1))
                print("    body = %s" % json.dumps(body, ensure_ascii=False))
                print("    r = s.post('%s', json=body, timeout=15)" % url)
                print("    return r.json()")
            except:
                print("# POST body 非 JSON，跳过")

        print()


if __name__ == "__main__":
    captures = load_captures()
    analyze_captures(captures)
    if "--generate" in sys.argv:
        generate_scraper(captures)
