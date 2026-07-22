# -*- coding: utf-8 -*-
"""
轻量级 HTTPS MITM 代理

能解密 HTTPS 流量，捕获东方财富 APP 的 API 请求。
使用 Python 内置模块，无需额外依赖。

使用方法：
  python scripts/https_mitm_proxy.py

然后在应用宝模拟器中设置代理为 电脑IP:8888
"""
import sys, io, os, json, time, socket, ssl, threading, select
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

CAPTURE_DIR = Path(r"D:\project\jiarenmens\data\captured")
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

TARGET_DOMAINS = [
    "emdcspzhapi", "emstockdiag", "groupwap", "emcreative",
    "spzhapi", "push2em", "empts", "emzuhelist",
    "eastmoney", "dfcfs",
]

captured = []


def generate_ca():
    """生成 CA 证书（用于 MITM 解密 HTTPS）"""
    import subprocess
    ca_dir = Path(r"D:\project\jiarenmens\data\ca")
    ca_dir.mkdir(parents=True, exist_ok=True)

    ca_key = ca_dir / "ca.key"
    ca_cert = ca_dir / "ca.crt"

    if ca_cert.exists():
        return str(ca_key), str(ca_cert)

    # 生成 CA 私钥
    subprocess.run([
        "openssl", "genrsa", "-out", str(ca_key), "2048"
    ], capture_output=True, check=True)

    # 生成 CA 证书
    subprocess.run([
        "openssl", "req", "-new", "-x509", "-days", "3650",
        "-key", str(ca_key), "-out", str(ca_cert),
        "-subj", "/CN=EastMoney MITM CA/O=MITM/C=CN"
    ], capture_output=True, check=True)

    print("CA 证书已生成: %s" % ca_cert)
    print("请将此证书安装到模拟器中！")
    return str(ca_key), str(ca_cert)


def generate_cert(domain, ca_key_path, ca_cert_path):
    """为指定域名生成证书"""
    import subprocess
    cert_dir = Path(r"D:\project\jiarenmens\data\ca\certs")
    cert_dir.mkdir(parents=True, exist_ok=True)

    key_path = cert_dir / "%s.key" % domain.replace(".", "_")
    cert_path = cert_dir / "%s.crt" % domain.replace(".", "_")

    if cert_path.exists():
        return str(key_path), str(cert_path)

    # 生成域名私钥
    subprocess.run([
        "openssl", "genrsa", "-out", str(key_path), "2048"
    ], capture_output=True, check=True)

    # 生成证书签名请求
    csr_path = cert_dir / "%s.csr" % domain.replace(".", "_")
    subprocess.run([
        "openssl", "req", "-new", "-key", str(key_path),
        "-out", str(csr_path), "-subj", "/CN=%s" % domain
    ], capture_output=True, check=True)

    # 用 CA 签发证书
    subprocess.run([
        "openssl", "x509", "-req", "-days", "365",
        "-in", str(csr_path), "-CA", ca_cert_path,
        "-CAkey", ca_key_path, "-CAcreateserial",
        "-out", str(cert_path)
    ], capture_output=True, check=True)

    return str(key_path), str(cert_path)


class MITMProxyHandler(BaseHTTPRequestHandler):
    """MITM 代理处理器"""

    ca_key_path = None
    ca_cert_path = None

    def log_message(self, format, *args):
        pass

    def do_CONNECT(self):
        """处理 HTTPS CONNECT 请求 - 建立 MITM 隧道"""
        host, port = self.path.split(":")
        port = int(port)

        # 检查是否是目标域名
        is_target = any(d in host for d in TARGET_DOMAINS)

        if not is_target:
            # 非目标域名，直接隧道转发
            self._tunnel(host, port)
            return

        # 目标域名：建立 MITM 连接
        try:
            # 生成域名证书
            key_path, cert_path = generate_cert(
                host, self.ca_key_path, self.ca_cert_path
            )

            # 告诉客户端隧道已建立
            self.send_response(200, "Connection Established")
            self.end_headers()

            # 将客户端连接包装为 SSL
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert_path, key_path)

            try:
                self.connection = context.wrap_socket(
                    self.connection, server_side=True
                )
            except ssl.SSLError as e:
                # SSL 握手失败（客户端可能不信任我们的 CA）
                return

            # 连接到真实服务器
            remote = socket.create_connection((host, port))
            remote_context = ssl.create_default_context()
            remote = remote_context.wrap_socket(remote, server_hostname=host)

            # 双向转发数据并捕获
            self._mitm_forward(host, port, remote)

        except Exception as e:
            pass

    def _tunnel(self, host, port):
        """简单隧道转发（不解密）"""
        try:
            remote = socket.create_connection((host, port))
            self.send_response(200, "Connection Established")
            self.end_headers()

            sockets = [self.connection, remote]
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 30)
                if exceptional:
                    break
                for s in readable:
                    data = s.recv(8192)
                    if not data:
                        return
                    if s is self.connection:
                        remote.send(data)
                    else:
                        self.connection.send(data)
        except:
            pass
        finally:
            try:
                remote.close()
            except:
                pass

    def _mitm_forward(self, host, port, remote):
        """MITM 转发：双向转发并解析 HTTP 流量"""
        import re

        client = self.connection
        sockets = [client, remote]
        client_buf = b""
        remote_buf = b""

        while True:
            try:
                readable, _, exceptional = select.select(sockets, [], sockets, 30)
            except:
                break

            if exceptional:
                break

            for s in readable:
                try:
                    data = s.recv(65536)
                except:
                    return

                if not data:
                    return

                if s is client:
                    # 客户端 -> 服务器
                    client_buf += data
                    try:
                        remote.send(data)
                    except:
                        return

                    # 尝试解析 HTTP 请求
                    self._parse_request(host, client_buf)

                else:
                    # 服务器 -> 客户端
                    remote_buf += data
                    try:
                        client.send(data)
                    except:
                        return

                    # 尝试解析 HTTP 响应
                    self._parse_response(host, remote_buf)

    def _parse_request(self, host, buf):
        """解析 HTTP 请求"""
        try:
            text = buf.decode("utf-8", errors="replace")
            if "\r\n\r\n" not in text:
                return

            header_part, body_part = text.split("\r\n\r\n", 1)
            lines = header_part.split("\r\n")
            if not lines:
                return

            method, path, _ = lines[0].split(" ", 2)

            # 记录请求
            req_info = {
                "host": host,
                "method": method,
                "path": path,
                "body": body_part[:5000] if body_part else "",
            }

            # 保存到文件
            ts = int(time.time() * 1000)
            safe_path = path.split("?")[0].replace("/", "_").strip("_") or "root"
            filename = "req_%s_%s_%s.json" % (host.replace(".", "_"), safe_path[:30], ts)
            filepath = CAPTURE_DIR / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(req_info, f, ensure_ascii=False, indent=2)

            print("[REQ] %s %s%s (saved: %s)" % (method, host, path[:80], filename))

        except:
            pass

    def _parse_response(self, host, buf):
        """解析 HTTP 响应"""
        try:
            # 检查是否有完整的 HTTP 响应
            text = buf.decode("utf-8", errors="replace")
            if "\r\n\r\n" not in text:
                return

            header_part, body_part = text.split("\r\n\r\n", 1)
            lines = header_part.split("\r\n")
            if not lines:
                return

            status_line = lines[0]
            status_code = int(status_line.split(" ", 2)[1])

            # 保存响应
            ts = int(time.time() * 1000)
            filename = "resp_%s_%s.json" % (host.replace(".", "_"), ts)
            filepath = CAPTURE_DIR / filename

            resp_info = {
                "host": host,
                "status": status_code,
                "body": body_part[:10000],
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(resp_info, f, ensure_ascii=False, indent=2)

            # 检查是否有数据
            try:
                d = json.loads(body_part)
                result = d.get("result", d.get("RCode", "?"))
                msg = str(d.get("message", ""))[:60]
                print("[RESP] %s %d result=%s msg=%s" % (host, status_code, result, msg))
            except:
                print("[RESP] %s %d (%d bytes)" % (host, status_code, len(body_part)))

        except:
            pass


def main():
    # 检查 openssl 是否可用
    import subprocess
    try:
        subprocess.run(["openssl", "version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("错误：需要安装 OpenSSL")
        print("Windows 用户可以安装 Git for Windows（自带 openssl）")
        print("或下载：https://slproweb.com/products/Win32OpenSSL.html")
        return

    # 生成 CA 证书
    ca_key, ca_cert = generate_ca()
    MITMProxyHandler.ca_key_path = ca_key
    MITMProxyHandler.ca_cert_path = ca_cert

    port = 8888
    server = HTTPServer(("0.0.0.0", port), MITMProxyHandler)

    print("=" * 60)
    print("东方财富 APP HTTPS MITM 代理")
    print("=" * 60)
    print("监听端口: %d" % port)
    print("CA 证书: %s" % ca_cert)
    print("捕获目录: %s" % CAPTURE_DIR)
    print()
    print("重要：需要在模拟器中安装 CA 证书！")
    print("  1. 将 %s 传到模拟器中" % ca_cert)
    print("  2. 在模拟器 设置 → 安全 → 安装证书 中安装")
    print("  3. 然后设置 WiFi 代理为 电脑IP:%d" % port)
    print()
    print("按 Ctrl+C 停止")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止！共捕获 %d 个请求" % len(captured))
        server.shutdown()


if __name__ == "__main__":
    main()
