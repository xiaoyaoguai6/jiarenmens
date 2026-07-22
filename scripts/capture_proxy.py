# -*- coding: utf-8 -*-
"""
东方财富 APP 抓包代理服务器

用途：拦截东方财富 APP 的 API 请求，记录完整的请求参数和响应。
配合应用宝/安卓模拟器使用。

使用方法：
1. 运行此脚本: python scripts/capture_proxy.py
2. 在应用宝/模拟器中设置代理: 电脑IP:8888
3. 在东方财富 APP 中浏览实盘组合页面
4. 所有 API 请求会保存到 data/captured/ 目录
"""
import sys, io, os, json, time, threading
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from pathlib import Path
import requests

CAPTURE_DIR = Path(r"D:\project\jiarenmens\data\captured")
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

# 只捕获东方财富相关的请求
TARGET_DOMAINS = [
    "emdcspzhapi.dfcfs.cn",
    "emstockdiag.eastmoney.com",
    "groupwap.eastmoney.com",
    "emcreative.eastmoney.com",
    "spzhapi.dfcfs.cn",
    "push2em.eastmoney.com",
    "empts.eastmoney.com",
    "emzuhelist.eastmoney.com",
]

captured_requests = []
lock = threading.Lock()


class CaptureHandler(BaseHTTPRequestHandler):
    """HTTP 代理请求处理器"""

    def log_message(self, format, *args):
        # 静默常规日志
        pass

    def do_CONNECT(self):
        """处理 HTTPS CONNECT 请求（隧道代理）"""
        # 对于 HTTPS，我们建立隧道但不解密
        # 用户需要在模拟器中安装证书才能解密 HTTPS
        self.send_response(200, 'Connection Established')
        self.end_headers()

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def _handle_request(self, method):
        url = self.path
        if url.startswith("/"):
            # 直接请求（非代理）
            return

        parsed = urlparse(url)
        domain = parsed.hostname

        # 检查是否是目标域名
        is_target = any(d in (domain or "") for d in TARGET_DOMAINS)

        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if is_target:
            self._capture_and_forward(method, url, parsed, body)
        else:
            self._forward(method, url, parsed, body)

    def _capture_and_forward(self, method, url, parsed, body):
        """捕获并转发请求"""
        domain = parsed.hostname
        path = parsed.path

        print("\n" + "=" * 60)
        print("[%s] %s %s" % (method, domain, path))
        if parsed.query:
            print("  Query: %s" % parsed.query[:200])
        if body:
            try:
                body_str = body.decode("utf-8", errors="replace")
                print("  Body: %s" % body_str[:300])
            except:
                print("  Body: <binary %d bytes>" % len(body))

        # 转发请求
        try:
            headers = dict(self.headers)
            headers.pop("Host", None)
            headers.pop("Proxy-Connection", None)

            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=30, verify=False)
            else:
                content_type = headers.get("Content-Type", "")
                if "json" in content_type:
                    resp = requests.post(url, json=json.loads(body) if body else {}, headers=headers, timeout=30, verify=False)
                else:
                    resp = requests.post(url, data=body, headers=headers, timeout=30, verify=False)

            # 记录捕获的数据
            capture = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "method": method,
                "url": url,
                "domain": domain,
                "path": path,
                "query": parsed.query,
                "request_headers": dict(self.headers),
                "request_body": body.decode("utf-8", errors="replace")[:5000] if body else "",
                "response_status": resp.status_code,
                "response_headers": dict(resp.headers),
                "response_body": resp.text[:10000],
            }

            with lock:
                captured_requests.append(capture)

            # 保存到文件
            ts = int(time.time() * 1000)
            filename = "%s_%s_%s.json" % (domain.replace(".", "_"), path.replace("/", "_").strip("_") or "root", ts)
            filepath = CAPTURE_DIR / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(capture, f, ensure_ascii=False, indent=2)

            print("  => [%d] %s (saved: %s)" % (resp.status_code, resp.text[:100], filename))

            # 返回响应
            self.send_response(resp.status_code)
            for key, value in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(resp.content)

        except Exception as e:
            print("  => ERROR: %s" % e)
            self.send_error(502, str(e))

    def _forward(self, method, url, parsed, body):
        """直接转发非目标请求"""
        try:
            headers = dict(self.headers)
            headers.pop("Host", None)
            headers.pop("Proxy-Connection", None)

            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=30, verify=False)
            else:
                resp = requests.post(url, data=body, headers=headers, timeout=30, verify=False)

            self.send_response(resp.status_code)
            for key, value in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(resp.content)
        except:
            self.send_error(502)


def main():
    port = 8888
    server = HTTPServer(("0.0.0.0", port), CaptureHandler)
    print("=" * 60)
    print("东方财富 APP 抓包代理服务器")
    print("=" * 60)
    print("监听端口: %d" % port)
    print("捕获目录: %s" % CAPTURE_DIR)
    print()
    print("使用方法:")
    print("  1. 在应用宝/模拟器的 WiFi 设置中配置代理:")
    print("     代理地址: <你电脑的IP>")
    print("     端口: %d" % port)
    print("  2. 打开东方财富 APP")
    print("  3. 进入 '实盘组合' -> 点击任意组合查看详情")
    print("  4. 所有 API 请求会自动捕获并保存")
    print()
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n停止服务器...")
        print("共捕获 %d 个请求" % len(captured_requests))
        server.shutdown()


if __name__ == "__main__":
    main()
