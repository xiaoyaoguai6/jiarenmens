# -*- coding: utf-8 -*-
"""
使用 proxy.py 的 HTTPS 拦截插件

捕获东方财富 APP 的 API 请求，包括 HTTPS 流量。

使用方法：
  python scripts/mitm_capture.py

在模拟器中设置代理为 电脑IP:8888
首次使用需要在模拟器中安装 CA 证书（脚本会自动提示）
"""
import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path

try:
    from proxy import Proxy
    from proxy.http.proxy import HttpProxyPlugin
    from proxy.http.parser import HttpParser
    from proxy.http.methods import httpMethods
    from proxy.common.utils import build_http_response
    from proxy.core.connection import TcpClientConnection
except ImportError:
    print("需要安装 proxy.py: pip install proxy.py")
    sys.exit(1)

CAPTURE_DIR = Path(r"D:\project\jiarenmens\data\captured")
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

TARGET_DOMAINS = [
    "emdcspzhapi", "emstockdiag", "groupwap", "emcreative",
    "spzhapi", "push2em", "empts", "emzuhelist",
    "eastmoney", "dfcfs",
]


class EastMoneyCapturePlugin(HttpProxyPlugin):
    """东方财富 API 捕获插件"""

    def before_upstream_connection(self, request: HttpParser):
        return request

    def handle_client_request(self, request: HttpParser):
        host = request.host or ""
        if not any(d in host for d in TARGET_DOMAINS):
            return

        method = request.method
        path = request.path or ""
        body = request.body or b""

        print("[REQ] %s %s%s" % (
            method.decode() if isinstance(method, bytes) else method,
            host,
            (path.decode() if isinstance(path, bytes) else path)[:100]
        ))

        # 保存请求
        ts = int(time.time() * 1000)
        req_info = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": method.decode() if isinstance(method, bytes) else str(method),
            "host": host,
            "path": path.decode() if isinstance(path, bytes) else str(path),
            "body": body.decode("utf-8", errors="replace")[:5000],
        }

        filename = "req_%s_%s.json" % (host.replace(".", "_"), ts)
        filepath = CAPTURE_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(req_info, f, ensure_ascii=False, indent=2)

    def on_upstream_connection(self, request: HttpParser):
        pass

    def on_response(self, request: HttpParser, response: HttpParser):
        host = request.host or ""
        if not any(d in host for d in TARGET_DOMAINS):
            return

        body = response.body or b""
        status = response.code or 0

        print("[RESP] %s %s (%d bytes)" % (host, status, len(body)))

        # 保存响应
        ts = int(time.time() * 1000)
        resp_info = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "host": host,
            "status": status,
            "body": body.decode("utf-8", errors="replace")[:20000],
        }

        try:
            d = json.loads(body)
            result = d.get("result", d.get("RCode", "?"))
            msg = str(d.get("message", ""))[:60]
            resp_info["parsed_result"] = result
            resp_info["parsed_msg"] = msg
            print("  => result=%s msg=%s" % (result, msg))

            data = d.get("data")
            if data and isinstance(data, list) and data:
                print("  => DATA: list[%d] keys=%s" % (len(data), list(data[0].keys())[:10]))
        except:
            pass

        filename = "resp_%s_%s.json" % (host.replace(".", "_"), ts)
        filepath = CAPTURE_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(resp_info, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 60)
    print("东方财富 APP HTTPS 拦截代理")
    print("=" * 60)
    print("监听: 0.0.0.0:8888")
    print("捕获目录: %s" % CAPTURE_DIR)
    print()
    print("在模拟器中设置代理: 电脑IP:8888")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    proxy = Proxy(
        port=8888,
        num_workers=4,
        plugins=[EastMoneyCapturePlugin],
    )
    proxy.run()


if __name__ == "__main__":
    main()
