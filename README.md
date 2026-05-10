# 东方财富实盘选手爬虫

爬取东方财富实盘组合榜单数据，包括选手信息、持仓明细和历史调仓记录。

## 功能特性

- **异步并发爬取** - 使用 asyncio + Playwright，单选手内三类数据真正并行
- **浏览器连接池** - 浏览器实例复用，Context 池化管理，避免频繁创建/销毁开销
- **反检测机制** - 自定义 UserAgent、viewport、locale、时区，绕过网站反爬限制
- **SQLite 高效存储** - 日期隔离存储，支持按日期分析查询，批量写入优化
- **断点续传** - Ctrl+C 中断后可继续，自动保存检查点
- **跨平台兼容** - 支持 Windows 和 Linux（Ubuntu），自动适配 Chromium 启动参数
- **代理池支持** - 可配置代理避免被封

## 安装依赖

### Windows

```bash
pip install -r requirements.txt
playwright install chromium
```

### Ubuntu / Linux

```bash
pip install -r requirements.txt
playwright install chromium

# 安装 Chromium 系统依赖（必需！）
sudo playwright install-deps chromium

# 安装中文字体（页面渲染必需）
sudo apt-get install -y fonts-noto-cjk
```

主要依赖：
- `requests` - HTTP 请求
- `playwright` - 动态页面渲染
- `beautifulsoup4` - HTML 解析
- `aiohttp` - 异步 HTTP

## 快速开始

```bash
# 默认爬取（每榜单 500 名，并发 20）
python main.py

# 测试模式（只处理 10 个选手）
python main.py --test

# 指定每榜单 100 名，并发 30
python main.py --limit 100 --workers 30
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--limit` | 500 | 每榜单爬取数量 |
| `--workers` | 20 | 并发数 |
| `--test` | false | 测试模式，只处理 10 个选手 |
| `--no-skip` | false | 不跳过已存在的选手数据 |
| `--checkpoint-reset` | false | 重置检查点 |
| `--analyze` | false | 运行持仓分析 |

## 数据存储

数据存储在 `data/crawl_data.db`（SQLite），持仓和调仓数据按 `crawl_date` 字段隔离，多天运行不会互相干扰：

```sql
-- 选手表（每个选手唯一）
players (
    zh_id TEXT PRIMARY KEY,
    name, followers, total_return, daily_return,
    net_value, max_drawdown, win_rate, days, concept, ...
)

-- 持仓表（按 crawl_date 隔离）
positions (
    id INTEGER PRIMARY KEY,
    zh_id, stock_code, stock_name,
    cost_price, current_price, profit_ratio, position_ratio,
    crawl_date TEXT,  -- 爬取日期，如 '2026-05-10'
    ...
)

-- 调仓表（按 crawl_date 隔离）
trades (
    id INTEGER PRIMARY KEY,
    zh_id, stock_code, stock_name, trade_date,
    direction, position_change, position_ratio,
    crawl_date TEXT,  -- 爬取日期，如 '2026-05-10'
    ...
)
```

## 持仓分析

```bash
# 分析最新数据
python main.py --analyze
```

分析报告包含：
- **持仓最多的股票 Top 20** - 被多少选手持有、平均仓位、平均盈利
- **选手仓位分布** - 空仓、1成以下、3成以下、3-5成、5-7成、7-9成、9成以上
- **股票盈亏分布** - 按盈利区间分类
- **当日盈利最高的选手 Top 10**

## 使用代理池

在 `proxies.txt` 中添加代理：

```txt
# proxies.txt
http://127.0.0.1:7890
http://user:password@192.168.1.1:8080
```

启用代理池：
```bash
export USE_PROXY_POOL=true
python main.py
```

## 项目结构

```
dfcfshipan/
├── main.py                      # 入口文件
├── requirements.txt             # 依赖列表
├── proxies.txt                  # 代理列表（可选）
├── data/
│   ├── checkpoint.json         # 爬取检查点
│   └── crawl_data.db           # SQLite 数据库
└── src/
    ├── config.py              # 配置（URL、路径等）
    ├── spiders/              # 爬虫模块
    │   ├── base.py           # 异步基础爬虫类
    │   ├── player_list.py    # 选手列表爬虫（API）
    │   ├── player_detail.py   # 选手详情爬虫
    │   ├── position.py        # 持仓数据爬虫
    │   └── trade.py          # 调仓记录爬虫
    ├── storage/              # 存储模块
    │   ├── interface.py      # 存储接口抽象
    │   ├── sqlite_storage.py  # SQLite 存储实现
    │   └── storage_factory.py # 存储工厂
    ├── analysis/              # 分析模块
    │   └── position_analyzer.py  # 持仓分析器
    └── utils/                 # 工具模块
        ├── logger.py           # 日志配置
        ├── proxy_pool.py      # 代理池管理
        └── async_playwright_pool.py  # 异步 Playwright 连接池
```

## 技术架构

### 异步爬取流程

```
1. 获取选手列表 (API)
       ↓
2. 创建 AsyncPlaywrightPool (复用浏览器)
   - Chromium 启动参数: --no-sandbox, --disable-dev-shm-usage 等
   - Context 反检测配置: Windows Chrome UA, zh-CN locale, Asia/Shanghai 时区
       ↓
3. 对每个选手：
   ┌─────────────────────────────────────┐
   │  asyncio.gather() 并行执行:          │
   │    - fetch_player_detail (详情)       │
   │    - fetch_positions (持仓)          │
   │    - fetch_trades (调仓)            │
   └─────────────────────────────────────┘
       ↓
4. 批量存入 SQLite (每 50 个选手)
   - 按 crawl_date 隔离数据
       ↓
5. 每 50 个选手保存检查点（原子写入）
```

### 浏览器连接池

- 单个 Playwright + Browser 实例启动一次
- 多个 BrowserContext 组成连接池
- 使用 Semaphore 控制并发，无需额外锁
- Context 创建时自动配置反检测参数

### 断点续传

```
1. 启动爬虫，加载 checkpoint.json
2. 跳过 completed_ids 中的选手
3. Ctrl+C 中断 → 自动保存检查点 + 批量数据
4. 重新启动 → 从断点继续
```

## 注意事项

1. **Ubuntu 用户必须运行 `sudo playwright install-deps chromium`**，否则 Chromium 无法启动
2. **缺少中文字体**会导致页面 JS 渲染异常，运行 `sudo apt-get install fonts-noto-cjk`
3. **并发数建议 10-20**，过高可能被网站限流
4. **自动重试机制**，失败自动重试 3 次，被反爬拦截时会打印页面片段到日志
5. **调仓记录需要滚动加载**，爬取较慢
6. **建议使用代理池**避免被封

## 故障排查

### 页面全部爬取为空

查看 `logs/spider.log`，常见原因：

| 日志内容 | 原因 | 解决方案 |
|----------|------|---------|
| `Chromium 浏览器启动成功` 后无后续 | Context 创建或页面获取超时 | 检查网络连接，降低 `--workers` 并发数 |
| `页面可能被拦截` + 页面片段 | 网站 WAF 反爬 | 使用代理池，降低并发，增加等待时间 |
| `Unable to connect to browser` | Chromium 系统依赖缺失 | 运行 `sudo playwright install-deps chromium` |
| `Failed to launch browser` | 缺少运行时库 | 检查 `playwright install chromium` 是否执行 |
| `未能从页面提取 xxxx` | 网站改版或反爬 | 看日志中页面片段是否包含正常数据 |
| `timeout: exceeded 60000ms` | 页面加载超时 | 网络较慢时增大 `--workers` 会加剧超时，建议调小 |

## 榜单 API 映射

| 榜单标签 | rankType | rateTitle |
|----------|----------|-----------|
| 总榜 | 10004 | 总收益 |
| 年榜 | 10003 | 250日收益 |
| 月榜 | 10001 | 20日收益 |
| 周榜 | 10000 | 5日收益 |
| 日榜 | 10005 | 日收益 |
