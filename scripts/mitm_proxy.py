# -*- coding: utf-8 -*-
"""
能解密 HTTPS 的 MITM 代理

使用 Git 自带的 OpenSSL 生成证书。
在模拟器中安装 CA 证书后即可解密东方财富 APP 的 HTTPS 流量。

使用方法：
  1. python scripts/mitm_proxy.py
  2. 将 data/ca/mitm-ca.crt 传到模拟器中并安装
  3. 模拟器设置代理为 电脑IP:8888
  4. 打开东方财富 APP 浏览实盘组合
"""
import sys, io, os, json, time, socket, ssl, subprocess, threading, select, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

OPENSSL = r"C:\Program Files\Git\usr\bin\openssl.exe"
CA_DIR = Path(r"D:\project\jiarenmens\data\ca")
CERTS_DIR = CA_DIR / "certs"
CAPTURE_DIR = Path(r"D:\project\jiarenmens\data\captured")

for d in [CA_DIR, CERTS_DIR, CAPTURE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CA_KEY = CA_DIR / "ca.key"
CA_CERT = CA_DIR / "ca.crt"

TARGET_DOMAINS = [
    "emdcspzhapi", "emstockdiag", "groupwap", "emcreative",
    "spzhapi", "push2em", "empts", "emzuhelist", "dfcfs",
]


def run_openssl(args):
    """运行 OpenSSL 命令"""
    cmd = [OPENSSL] + args
    result = subprocess.run(cmd, capture_output=True, timeout=10)
    return result.returncode == 0


def ensure_ca():
    """确保 CA 证书存在"""
    if CA_KEY.exists() and CA_CERT.exists():
        return True

    print("生成 CA 证书...")
    # 生成 CA 私钥
    if not run_openssl(["genrsa", "-out", str(CA_KEY), "2048"]):
        print("生成 CA 私钥失败")
        return False

    # 生成 CA 证书
    if not run_openssl(["req", "-new", "-x509", "-days", "3650",
                        "-key", str(CA_KEY), "-out", str(CA_CERT),
                        "-subj", "/CN=MITM CA/O=MITM/C=CN"]):
        print("生成 CA 证书失败")
        return False

    print("CA 证书已生成: %s" % CA_CERT)
    print("请将此文件传到模拟器中并安装！")
    return True


def ensure_domain_cert(domain):
    """确保域名证书存在"""
    key_file = CERTS_DIR / ("%s.key" % domain.replace(".", "_"))
    cert_file = CERTS_DIR / ("%s.crt" % domain.replace(".", "_"))

    if key_file.exists() and cert_file.exists():
        return str(key_file), str(cert_file)

    # 生成域名私钥
    run_openssl(["genrsa", "-out", str(key_file), "2048"])

    # 生成 CSR
    csr_file = CERTS_DIR / ("%s.csr" % domain.replace(".", "_"))
    run_openssl(["req", "-new", "-key", str(key_file),
                 "-out", str(csr_file), "-subj", "/CN=%s" % domain])

    # 用 CA 签发
    run_openssl(["x509", "-req", "-days", "365",
                 "-in", str(csr_file), "-CA", str(CA_CERT),
                 "-CAkey", str(CA_KEY), "-CAcreateserial",
                 "-out", str(cert_file)])

    return str(key_file), str(cert_file)


def capture_request(domain, method, path, headers, body, resp_status, resp_body):
    """保存捕获的请求"""
    ts = int(time.time() * 1000)
    safe = path.split("?")[0].replace("/", "_").strip("_")[:40] or "root"
    filename = "%s_%s_%s.json" % (domain.replace(".", "_"), safe, ts)

    # 尝试解析响应 JSON
    parsed = {}
    try:
        d = json.loads(resp_body)
        parsed["result"] = d.get("result", d.get("RCode", "?"))
        parsed["message"] = str(d.get("message", d.get("error", "")))[:100]
        data = d.get("data")
        if data and isinstance(data, list) and data:
            parsed["data_count"] = len(data)
            parsed["data_keys"] = list(data[0].keys())[:15]
        elif data and isinstance(data, dict):
            parsed["data_keys"] = list(data.keys())[:15]
    except:
        pass

    capture = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": method,
        "domain": domain,
        "path": path,
        "request_headers": dict(headers) if headers else {},
        "request_body": body[:5000] if body else "",
        "response_status": resp_status,
        "response_body": resp_body[:20000],
        "parsed": parsed,
    }

    filepath = CAPTURE_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(capture, f, ensure_ascii=False, indent=2)

    return filename


class MITMHandler(BaseHTTPRequestHandler):
    """MITM 代理处理器"""

    def log_message(self, fmt, *args):
        pass

    def do_CONNECT(self):
        """HTTPS CONNECT 请求"""
        host, port = self.path.split(":", 1)
        port = int(port)
        is_target = any(d in host for d in TARGET_DOMAINS)

        if not is_target:
            # 非目标：直接隧道
            self._tunnel(host, port)
            return

        # 目标域名：MITM 解密
        try:
            key_path, cert_path = ensure_domain_cert(host)

            # 通知客户端隧道已建立
            self.send_response(200, "Connection Established")
            self.end_headers()

            # 用我们的证书与客户端建立 SSL
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert_path, key_path)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            try:
                client_ssl = ctx.wrap_socket(self.connection, server_side=True)
            except Exception:
                return

            # 与真实服务器建立 SSL
            remote_sock = socket.create_connection((host, port))
            remote_ctx = ssl.create_default_context()
            remote_ctx.check_hostname = False
            remote_ctx.verify_mode = ssl.CERT_NONE
            remote_ssl = remote_ctx.wrap_socket(remote_sock, server_hostname=host)

            # 双向转发并捕获
            self._mitm_relay(host, port, client_ssl, remote_ssl)

        except Exception:
            pass

    def _tunnel(self, host, port):
        """简单隧道"""
        try:
            remote = socket.create_connection((host, port))
            self.send_response(200, "Connection Established")
            self.end_headers()
            self._relay(self.connection, remote)
        except:
            pass

    def _relay(self, sock1, sock2):
        """双向转发"""
        sockets = [sock1, sock2]
        try:
            while True:
                readable, _, err = select.select(sockets, [], sockets, 30)
                if err:
                    break
                for s in readable:
                    data = s.recv(65536)
                    if not data:
                        return
                    (sock2 if s is sock1 else sock1).sendall(data)
        except:
            pass
        finally:
            try:
                sock1.close()
            except:
                pass
            try:
                sock2.close()
            except:
                pass

    def _mitm_relay(self, host, port, client, remote):
        """MITM 双向转发 + HTTP 解析"""
        client_buf = b""
        remote_buf = b""
        sockets = [client, remote]

        try:
            while True:
                readable, _, err = select.select(sockets, [], sockets, 30)
                if err:
                    break

                for s in readable:
                    try:
                        data = s.recv(65536)
                    except (ssl.SSLError, ConnectionError):
                        return
                    if not data:
                        return

                    if s is client:
                        client_buf += data
                        try:
                            remote.sendall(data)
                        except:
                            return
                        # 解析 HTTP 请求
                        self._try_parse_request(host, client_buf)
                    else:
                        remote_buf += data
                        try:
                            client.sendall(data)
                        except:
                            return
                        # 解析 HTTP 响应
                        self._try_parse_response(host, remote_buf)
        except:
            pass
        finally:
            try:
                client.close()
            except:
                pass
            try:
                remote.close()
            except:
                pass

    def _try_parse_request(self, host, buf):
        """尝试解析 HTTP 请求"""
        try:
            sep = buf.find(b"\r\n\r\n")
            if sep < 0:
                return

            header = buf[:sep].decode("utf-8", errors="replace")
            body = buf[sep + 4:]
            lines = header.split("\r\n")
            parts = lines[0].split(" ", 2)
            if len(parts) < 2:
                return

            method = parts[0]
            path = parts[1]

            # 解析 headers
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip()] = v.strip()

            # 存储请求信息供响应解析使用
            self._last_req = {
                "host": host, "method": method, "path": path,
                "headers": headers, "body": body.decode("utf-8", errors="replace")[:5000],
            }

            print("[REQ] %s %s%s" % (method, host, path[:100]))

        except:
            pass

    def _try_parse_response(self, host, buf):
        """尝试解析 HTTP 响应"""
        try:
            sep = buf.find(b"\r\n\r\n")
            if sep < 0:
                return

            header = buf[:sep].decode("utf-8", errors="replace")
            body = buf[sep + 4:]
            lines = header.split("\r\n")
            status_parts = lines[0].split(" ", 2)
            if len(status_parts) < 2:
                return

            status = int(status_parts[1])
            body_text = body.decode("utf-8", errors="replace")

            req = getattr(self, "_last_req", {})
            method = req.get("method", "?")
            path = req.get("path", "?")

            # 保存
            filename = capture_request(
                host, method, path,
                req.get("headers", {}), req.get("body", ""),
                status, body_text,
            )

            # 检查是否有数据
            try:
                d = json.loads(body_text)
                result = d.get("result", d.get("RCode", "?"))
                msg = str(d.get("message", ""))[:60]
                print("[RESP] %s %d => result=%s msg=%s (%s)" % (host, status, result, msg, filename))

                data = d.get("data")
                if data and isinstance(data, list) and data:
                    print("  ** DATA: list[%d] keys=%s" % (len(data), list(data[0].keys())[:10]))
            except:
                if len(body) > 100:
                    print("[RESP] %s %d (%d bytes) (%s)" % (host, status, len(body), filename))

        except:
            pass


def main():
    if not ensure_ca():
        return

    port = 8888
    server = HTTPServer(("0.0.0.0", port), MITMHandler)

    print("=" * 60)
    print("东方财富 APP HTTPS MITM 代理")
    print("=" * 60)
    print("监听: 0.0.0.0:%d" % port)
    print("CA 证书: %s" % CA_CERT)
    print("捕获目录: %s" % CAPTURE_DIR)
    print()
    print("【重要】首次使用步骤：")
    print("  1. 将 CA 证书传到模拟器:")
    print("     %s" % CA_CERT)
    print("  2. 在模拟器中: 设置 → 安全 → 加密与凭据 → 安装证书")
    print("  3. 设置 WiFi 代理: 电脑IP:%d" % port)
    print("  4. 打开东方财富 APP → 实盘 → 点击组合查看详情")
    print()
    print("按 Ctrl+C 停止")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
