# 东方财富 APP 抓包指南（雷电模拟器 + LSPosed 绕过 SSL Pinning）

## 概述

目标：在雷电模拟器中运行东方财富 APP，通过 LSPosed 模块绕过 SSL Pinning，配合代理工具抓取 APP 的实盘选手持仓 API 请求，获取之前被封禁的持仓数据。

**前置条件（已完成）：**
- 雷电模拟器，Android 14
- 已 Root
- 已安装 LSPosed 框架

## 第一步：安装 SSL Unpinning 模块

在 LSPosed 框架下，用 Xposed 模块绕过 SSL Pinning 比 Frida 更简单稳定。

### 1.1 下载模块（按推荐顺序）

**首选：TrustMeAlready**
- GitHub：https://github.com/ViRb3/TrustMeAlready/releases
- 最轻量，仅做一件事：禁用 SSL 证书验证
- 下载 APK 安装到模拟器

**备选一：JustTrustMe**
- GitHub：https://github.com/Fuzion24/JustTrustMe/releases
- 老牌模块，兼容性好
- 如果 TrustMeAlready 不生效再试这个

**备选二：SSLUnpinning**
- GitHub：https://github.com/nicogit/ssl-unpinning-xposed
- 另一个通用方案

**备选三：Play Integrity Fix（如果上述都不行）**
- 部分新版 APP 会检测 Xposed 环境，需要配合隐藏模块使用

### 1.2 在 LSPosed 中启用模块

1. 打开 **LSPosed Manager**
2. 进入 **模块** 页面
3. 找到刚安装的 TrustMeAlready（或其他模块）
4. 点击进入，**勾选启用**
5. 设置 **作用域**：
   - 只勾选 **东方财富**（包名：`com.eastmoney.android.berennsy`）
   - **不要**选全局作用域（可能影响其他 APP 的正常 SSL 连接）
6. 返回，**强制停止**东方财富 APP（长按 APP 图标 → 强制停止，或在设置里强制停止）
7. 重新打开东方财富 APP

### 1.3 验证模块生效

打开模拟器浏览器访问任意 HTTPS 网站（如 https://www.baidu.com），确认能正常访问（说明模块没有破坏系统 SSL）。

## 第二步：准备代理工具

你之前已有代理工具且能抓到其他页面。SSL Pinning 绕过后，持仓接口的请求就会出现在你的代理工具中。

如果想换用 mitmproxy（方便脚本化处理）：

```bash
pip install mitmproxy
```

启动：

```bash
# Web 界面版本（推荐，可视化过滤）
mitmweb --listen-port 8080

# 或纯命令行，保存所有流量
mitmdump -w eastmoney_capture.flow --listen-port 8080
```

首次启动后证书文件生成在：
- `C:\Users\<用户名>\.mitmproxy\`（Windows）
- `~/.mitmproxy/`（Linux/Mac）

### 2.1 安装代理证书到模拟器系统目录

你之前能抓到其他页面，说明代理和基础证书已经配好了。但为了确保万无一失，确认代理的 CA 证书已经安装到**系统证书目录**（而非用户证书目录）。

```bash
# 连接雷电模拟器（默认 adb 端口 5555，多开实例端口递增）
adb connect 127.0.0.1:5555

# 检查连接
adb devices

# 获取 root 权限
adb root
adb remount

# 查看系统证书目录，确认是否有你的代理证书
adb shell ls /system/etc/security/cacerts/ | head -20
```

如果没有，需要将证书推送到系统目录：

```bash
# 1. 计算证书哈希名（在电脑上执行）
openssl x509 -inform PEM -subject_hash_old -in your_proxy_ca.pem | head -1
# 输出类似：c8750f0d

# 2. 转换格式
openssl x509 -inform PEM -in your_proxy_ca.pem -out c8750f0d.0

# 3. 推送到系统证书目录
adb push c8750f0d.0 /system/etc/security/cacerts/
adb shell chmod 644 /system/etc/security/cacerts/c8750f0d.0

# 4. 重启模拟器
adb reboot
```

重启后可在 设置 → 安全 → 信任的凭据 → 系统 中确认证书已存在。

## 第三步：配置模拟器代理

如果之前已经配好代理，跳过此步。

在模拟器中：
1. 设置 → WLAN → 长按当前网络 → 修改网络
2. 代理改为 **手动**
3. 主机名：`10.0.2.2`（模拟器访问宿主机的地址，雷电也支持此地址）
4. 端口：你的代理工具端口（mitmproxy 默认 8080，看你之前用的工具）
5. 保存

## 第四步：抓取持仓 API 请求

### 4.1 启动代理工具

确保代理工具已启动并正在监听。

### 4.2 确认 LSPosed 模块已生效

强制停止东方财富 APP，重新打开。

### 4.3 在 APP 中操作

1. 打开东方财富 APP
2. 进入 **实盘大赛 / 实盘组合**
3. 点开任意一个选手的 **详情页**
4. 切换到 **持仓** 标签页
5. 再看看 **调仓记录**
6. 多点几个不同的选手

### 4.4 在代理工具中找到目标请求

在代理工具中过滤以下域名：
- `emdcspzhapi.dfcfs.cn` — H5 端 API 域名
- `emdcapi.eastmoney.com` — 可能的 APP 端 API 域名
- `push2.eastmoney.com` — 推送相关
- `*.dfcfs.cn` — 东方财富组合相关

重点关注包含以下关键词的请求：
- `rt_get_position` — 持仓数据
- `rt_get_info` — 选手详情
- `rt_get_change` / `rt_get_trade` — 调仓记录
- `position` / `detail` / `change`

### 4.5 记录请求信息

对于每个目标请求，记录：
1. **完整 URL**（包含域名和路径）
2. **请求方法**（GET/POST）
3. **所有 Headers**（尤其是 User-Agent、Cookie、自定义 Header）
4. **查询参数**（URL 中 ? 后面的参数）
5. **请求体**（如果是 POST）
6. **响应内容**（JSON 格式的持仓数据）

## 第五步：导出抓包结果（如果用 mitmproxy）

如果使用 mitmproxy，可以用以下脚本自动筛选和导出东方财富的 API 请求。

保存为 `filter_eastmoney.py`：

```python
"""
mitmproxy 脚本：自动筛选东方财富 API 请求并导出为 JSON
使用方式：mitmdump -r eastmoney_capture.flow -s filter_eastmoney.py
"""
import json
from mitmproxy import http

TARGET_HOSTS = [
    "emdcspzhapi.dfcfs.cn",
    "emdcapi.eastmoney.com",
    "push2.eastmoney.com",
    "dfcfs.cn",
    "eastmoney.com",
]

TARGET_KEYWORDS = [
    "position", "持仓",
    "rt_get_info", "rt_get_position", "rt_get_change",
    "detail", "change", "trade",
]

captured = []


def response(flow: http.HTTPFlow):
    host = flow.request.pretty_host
    if not any(h in host for h in TARGET_HOSTS):
        return

    url = flow.request.pretty_url
    entry = {
        "url": url,
        "method": flow.request.method,
        "host": host,
        "path": flow.request.path,
        "headers": dict(flow.request.headers),
        "query": dict(flow.request.query),
        "status": flow.response.status_code,
        "content_type": flow.response.headers.get("content-type", ""),
    }

    # 记录响应体
    try:
        entry["response_preview"] = flow.response.text[:1000]
        data = flow.response.json()
        if isinstance(data, dict):
            entry["response_keys"] = list(data.keys())
            entry["result"] = data.get("result")
            # 判断是否为有效数据（非 -10000 拒绝）
            if data.get("result") in ("0", 0) and data.get("data") and data["data"] != -10000:
                entry["has_real_data"] = True
            else:
                entry["has_real_data"] = False
    except Exception:
        pass

    captured.append(entry)

    # 实时打印
    has_data = entry.get("has_real_data", None)
    marker = "✓ DATA" if has_data else ("✗ BLOCKED" if has_data is False else "?")
    print(f"\n[{marker}] {flow.request.method} {url}")
    print(f"  Status: {flow.response.status_code}")
    if "response_preview" in entry:
        print(f"  Response: {entry['response_preview'][:200]}")


def done():
    """mitmproxy 退出时保存结果"""
    # 分组统计
    with_data = [e for e in captured if e.get("has_real_data")]
    blocked = [e for e in captured if e.get("has_real_data") is False]

    with open("captured_apis.json", "w", encoding="utf-8") as f:
        json.dump(captured, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"总计捕获 {len(captured)} 个东方财富请求")
    print(f"  ✓ 有真实数据: {len(with_data)}")
    print(f"  ✗ 被拒绝(-10000): {len(blocked)}")
    print(f"结果已保存到 captured_apis.json")

    if with_data:
        print(f"\n可用的 API 端点：")
        for e in with_data:
            print(f"  {e['method']} {e['url']}")
```

运行：

```bash
# 回放并筛选
mitmdump -r eastmoney_capture.flow -s filter_eastmoney.py

# 或者实时抓取时直接过滤
mitmdump -s filter_eastmoney.py --listen-port 8080
```

## 第六步：用 Python 复现 API 请求

把抓到的请求信息替换到以下模板中：

```python
"""
根据抓包结果复现东方财富 APP 的 API 请求
替换以下所有 "..." 为实际抓到的值
"""
import requests
import json

BASE_URL = "https://..."  # 从抓包中复制域名

# 从抓包中复制完整的 headers
HEADERS = {
    "User-Agent": "...",
    # 以下字段按需添加（从抓包中看到哪些就加哪些）：
    # "Referer": "...",
    # "Cookie": "...",
    # "Authorization": "...",
    # "X-Token": "...",
    # "EMProjJs-IPhone": "...",
}


def fetch_player_position(zh_id, uid=""):
    """获取选手持仓"""
    params = {
        "type": "rt_get_position",  # 或抓到的其他 type
        "zh": zh_id,
        "uid": uid,
        "appVer": "...",  # 从抓包中复制
    }
    resp = requests.get(f"{BASE_URL}/rtV1", params=params, headers=HEADERS, timeout=15)
    return resp.json()


def fetch_player_detail(zh_id, uid=""):
    """获取选手详情"""
    params = {
        "type": "rt_get_info",
        "zh": zh_id,
        "uid": uid,
        "appVer": "...",
    }
    resp = requests.get(f"{BASE_URL}/rtV1", params=params, headers=HEADERS, timeout=15)
    return resp.json()


def fetch_player_trades(zh_id, uid="", page=0, size=50):
    """获取选手调仓记录"""
    params = {
        "type": "rt_get_change",
        "zh": zh_id,
        "uid": uid,
        "recIdx": str(page * size),
        "recCnt": str(size),
        "appVer": "...",
    }
    resp = requests.get(f"{BASE_URL}/rtV1", params=params, headers=HEADERS, timeout=15)
    return resp.json()


# 测试
if __name__ == "__main__":
    print("=== 选手详情 ===")
    detail = fetch_player_detail("900013608")
    print(json.dumps(detail, ensure_ascii=False, indent=2))

    print("\n=== 选手持仓 ===")
    position = fetch_player_position("900013608")
    print(json.dumps(position, ensure_ascii=False, indent=2))
```

## 常见问题排查

### SSL Pinning 绕过不生效

| 症状 | 解决方案 |
|------|---------|
| 持仓页面仍然抓不到请求 | 模块未生效，检查 LSPosed 中是否正确启用并设置了作用域 |
| 代理显示 `SSL handshake failed` | SSL Pinning 未绕过，换一个模块试试 |
| 其他页面能抓但持仓不行 | 说明持仓接口有额外的证书固定，确认模块是针对系统级的 |
| 模块生效但 APP 闪退 | 模块版本不兼容 Android 14，换用更新版本或其他模块 |

### LSPosed 模块相关

| 症状 | 解决方案 |
|------|---------|
| 模块安装后 LSPosed 中看不到 | APK 可能未正确安装，重新安装 |
| 作用域中找不到东方财富 | 确认 APP 包名，在 LSPosed 中手动搜索 |
| 模块显示未激活 | 需要强制停止 APP 后重新打开 |
| Android 14 兼容性问题 | 优先用 TrustMeAlready（更新维护较好） |

### 代理连接问题

| 症状 | 解决方案 |
|------|---------|
| APP 显示网络错误 | 代理配置错误，检查 IP 和端口 |
| 只能看到 CONNECT 请求 | SSL Pinning 没绕过，不是证书问题 |
| 代理工具无任何请求 | 模拟器代理未配置或 IP 不对 |

### 雷电模拟器 adb 连接

```bash
# 雷电模拟器默认 adb 端口
# 雷电 9:  127.0.0.1:5555（单开）
# 多开实例: 端口递增（5557, 5559, ...）
# 可在雷电多开器中查看每个实例的 adb 端口

adb connect 127.0.0.1:5555
adb devices
```

### 确认东方财富 APP 包名

```bash
# 列出所有已安装的东方财富相关包
adb shell pm list packages | grep eastmoney
# 常见包名：
# com.eastmoney.android.berennsy  — 主 APP
# com.eastmoney.android.berennsy.test — 测试版
```

## 后续：集成到 jiarenmens 项目

抓到可用的 API 后，集成步骤：

1. **分析 captured_apis.json** — 找出持仓、详情、调仓三个接口的 URL 和参数格式
2. **更新 src/config.py** — 添加 APP 端 API 地址
3. **新建 src/spiders/app_player.py** — 使用 APP 端的 headers 和参数格式
4. **更新 main.py** — 调用新的 spider 获取持仓数据
5. **测试** — 对比抓包结果和 Python 复现结果是否一致

关键可能的差异点：
- APP 端可能使用不同的 API 域名
- APP 端的 User-Agent 不同（Android 而非 iPhone）
- 可能需要特殊的 Header 字段（如设备 ID、Token 等）
- appVer 版本号可能不同
