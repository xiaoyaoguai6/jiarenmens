# -*- coding: utf-8 -*-
"""
东方财富 APP MITM 代理脚本

配合 mitmproxy 使用，自动解密 HTTPS 流量，
捕获东方财富 APP 的所有 API 请求。

使用方法：
  mitmdump -s scripts/eastmoney_addon.py -p 8888 --listen-host 0.0.0.0
"""
import json, time, os
from pathlib import Path
from mitmproxy import http

CAPTURE_DIR = Path(r"D:\project\jiarenmens\data\captured")
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

TARGET_DOMAINS = [
    "emdcspzhapi", "emstockdiag", "groupwap", "emcreative",
    "spzhapi", "push2em", "empts", "emzuhelist",
    "eastmoney", "dfcfs",
]


def response(flow: http.HTTPFlow):
    url = flow.request.pretty_url
    domain = flow.request.pretty_host

    # 只捕获目标域名
    if not any(d in domain for d in TARGET_DOMAINS):
        return

    method = flow.request.method
    status = flow.response.status_code
    path = flow.request.path

    # 打印到控制台
    body_size = len(flow.response.content) if flow.response.content else 0
    print("[%s] %s %s -> %d (%d bytes)" % (method, domain, path, status, body_size))

    # 读取请求体
    req_body = ""
    if flow.request.content:
        try:
            req_body = flow.request.content.decode("utf-8", errors="replace")
        except:
            req_body = "<binary %d bytes>" % len(flow.request.content)

    # 读取响应体
    resp_body = ""
    if flow.response.content:
        try:
            resp_body = flow.response.content.decode("utf-8", errors="replace")
        except:
            resp_body = "<binary %d bytes>" % len(flow.response.content)

    # 保存到文件
    capture = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": method,
        "url": url,
        "domain": domain,
        "path": path,
        "query": flow.request.pretty_url.split("?", 1)[1] if "?" in flow.request.pretty_url else "",
        "request_headers": dict(flow.request.headers),
        "request_body": req_body[:10000],
        "response_status": status,
        "response_headers": dict(flow.response.headers),
        "response_body": resp_body[:20000],
    }

    ts = int(time.time() * 1000)
    safe_path = path.replace("/", "_").strip("_") or "root"
    filename = "%s_%s_%s.json" % (domain.replace(".", "_"), safe_path[:50], ts)
    filepath = CAPTURE_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(capture, f, ensure_ascii=False, indent=2)

    # 如果响应是 JSON，显示关键信息
    try:
        d = json.loads(resp_body)
        result = d.get("result", d.get("RCode", d.get("status", "?")))
        msg = str(d.get("message", d.get("error", "")))[:80]
        print("  => result=%s msg=%s (saved: %s)" % (result, msg, filename))

        # 检查是否有实际数据
        data = d.get("data")
        if data and isinstance(data, list) and data:
            print("  => DATA: list[%d] keys=%s" % (len(data), list(data[0].keys())[:10]))
        elif data and isinstance(data, dict):
            print("  => DATA: keys=%s" % list(data.keys())[:10])
    except:
        if body_size > 100:
            print("  => (non-json, %d bytes, saved: %s)" % (body_size, filename))
