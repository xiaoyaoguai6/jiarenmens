# 东方财富 APP 抓包指南

## 目标
通过应用宝在电脑运行东方财富 APP，用抓包代理捕获持仓 API 请求。

## 步骤

### 1. 启动抓包代理

```bash
cd D:\project\jiarenmens
python scripts/capture_proxy.py
```

服务器会监听 `0.0.0.0:8888`。

### 2. 查看你电脑的局域网 IP

```bash
ipconfig | findstr "IPv4"
```

记下类似 `192.168.x.x` 的地址。

### 3. 在应用宝中配置代理

1. 打开应用宝，启动安卓模拟器
2. 进入 **设置 → WLAN**
3. 长按当前 WiFi 网络 → **修改网络**
4. **代理** → 选择 **手动**
5. 填入：
   - 代理主机名：`你电脑的IP`（如 192.168.1.100）
   - 代理端口：`8888`
6. 保存

### 4. 操作东方财富 APP

1. 打开东方财富 APP
2. 进入 **实盘** → **实盘组合**
3. 随便点进一个组合，查看：
   - **持仓详情**（最重要！）
   - **调仓记录**
   - **选手信息**
4. 每个页面停留 3-5 秒，确保数据加载完成

### 5. 查看捕获结果

```bash
# 查看捕获的文件
ls data\captured\

# 分析捕获数据
python scripts/analyze_captures.py

# 分析并生成爬虫代码
python scripts/analyze_captures.py --generate
```

### 6. 注意事项

- **HTTPS 抓包**：应用宝模拟器可能需要安装 CA 证书才能解密 HTTPS
  - 在模拟器浏览器访问 `mitm.it` 下载证书
  - 或者：在模拟器设置中导入证书
- **证书固定**：东方财富 APP 可能有 SSL Pinning
  - 如果抓不到 HTTPS 请求，需要在模拟器中安装 Xposed + TrustMeAlready 模块
  - 或者使用 Frida 绕过 SSL Pinning
- **代理设置**：每次重启模拟器可能需要重新设置代理

### 7. 替代方案（如果抓包困难）

如果应用宝的代理设置不方便，可以考虑：

1. **Fiddler Classic**（Windows 原生）
   - 下载：https://www.telerik.com/fiddler
   - 配置简单，自动处理 HTTPS
   
2. **Charles Proxy**
   - 下载：https://www.charlesproxy.com
   - 界面友好，支持 SSL Proxying

3. **手机直接抓包**
   - 在手机上安装 HttpCanary（Android）
   - 直接在手机端捕获请求

## 捕获到数据后

我会分析捕获的 API 请求，提取：
- 完整的 URL 和参数
- 请求头（包含认证信息）
- 响应数据格式

然后实现 Python 爬虫，集成到现有项目中。
