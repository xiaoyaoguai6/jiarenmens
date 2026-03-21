# 家人们的实盘持仓

爬取东方财富实盘组合榜单数据，包括选手信息、持仓明细和历史调仓记录。

## 功能特性

- 爬取 5 个榜单（日榜/周榜/月榜/年榜/总榜）前 N 名选手
- 并发爬取提升速度（支持自定义并发数）
- 断点续传（跳过已存在的数据）
- 按时间戳存储数据
- 持仓分析功能（支持指定数据文件夹）
- 代理池支持
- Playwright 线程安全优化

## 安装依赖

```bash
pip install -r requirements.txt
```

依赖包：
- requests
- playwright
- beautifulsoup4
- lxml

安装 Playwright 浏览器：
```bash
playwright install chromium
```

## 使用方法

### 爬取数据

```bash
# 默认爬取（每榜单500名，并发20）
python main.py

# 指定每榜单100名，并发30
python main.py --limit 100 --workers 30

# 测试模式（只处理10个选手）
python main.py --test

# 强制重新爬取所有数据（不跳过已存在）
python main.py --no-skip
```

### 持仓分析

```bash
# 分析最新数据（使用 data/latest 软链接指向的数据）
python main.py --analyze

# 分析指定数据文件夹
python main.py --analyze --dir 20260322_011334
```

分析报告包含：
- 持仓最多的股票 Top 20
- 选手仓位分布（空仓、3成以下、3-5成、5-7成、7-9成、9成以上）
- 股票盈亏分布
- 当日盈利最高的选手 Top 10

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--limit` | 500 | 每榜单爬取数量 |
| `--workers` | 20 | 并发数 |
| `--test` | false | 测试模式，只处理10个选手 |
| `--no-skip` | false | 不跳过已存在的选手数据 |
| `--analyze` | false | 运行持仓分析 |
| `--dir` | latest | 分析时指定数据文件夹 |

### 爬取结果说明

```
成功: 0, 跳过: 46, 失败: 0
```

| 指标 | 含义 |
|------|------|
| **成功** | 新爬取并保存的选手数据（之前不存在） |
| **跳过** | 选手数据已存在，使用本地缓存未重新爬取 |
| **失败** | 爬取过程出错或未获取到数据 |

跳过是正常现象，说明这些选手之前已经爬取过。使用 `--no-skip` 可强制重新爬取。

## 使用代理池

#### 方式1: 代理文件

在 `proxies.txt` 中添加代理：

```txt
# proxies.txt
http://127.0.0.1:7890
http://user:password@192.168.1.1:8080
```

然后启用代理池：

```bash
export USE_PROXY_POOL=true
python main.py
```

#### 方式2: 环境变量

```bash
# 单个代理
export HTTP_PROXY="http://127.0.0.1:7890"
export USE_PROXY_POOL=true
python main.py
```

#### 方式3: 代码中添加

```python
from src.utils.proxy_pool import add_proxy

# 添加代理
add_proxy("http://127.0.0.1:7890")
add_proxy("http://user:pass@192.168.1.1:8080")
```

#### 验证代理

```python
from src.utils.proxy_pool import get_proxy_pool

pool = get_proxy_pool()
pool.check_all()  # 验证所有代理可用性
print(f"可用代理: {pool.working_count()}")
```

## 数据存储

```
data/
├── latest -> 20260322_011334/  # 最新数据的软链接
├── 20260322_011334/            # 按时间戳的文件夹
│   ├── players/                # 选手详情
│   │   ├── players.json       # 选手列表（合并去重后）
│   │   ├── 总榜.json          # 总榜选手列表
│   │   ├── 年榜.json          # 年榜选手列表
│   │   ├── 月榜.json          # 月榜选手列表
│   │   ├── 周榜.json          # 周榜选手列表
│   │   ├── 日榜.json          # 日榜选手列表
│   │   └── 900304915.json     # 单个选手详情
│   ├── positions/             # 持仓数据
│   │   └── 900304915.json     # 持仓 JSON 数组
│   └── trades/                # 调仓记录
│       └── 900304915.json     # 调仓 JSON 数组
└── 20260322_010957/           # 之前爬取的数据
    └── ...
```

## 数据字段

### 选手详情 (players/*.json)

```json
{
  "zh_id": "900304915",
  "name": "上能电气",
  "followers": 5,
  "total_return": -27.23,
  "daily_return": 2.5,
  "net_value": 0.728,
  "max_drawdown": 50.44,
  "win_rate": 45.83,
  "days": 138,
  "concept": "光伏概念"
}
```

### 持仓数据 (positions/*.json)

```json
[
  {
    "zh_id": "900304915",
    "stock_name": "上能电气",
    "stock_code": "300827",
    "cost_price": 15.5,
    "current_price": 18.2,
    "profit_ratio": 17.4,
    "position_ratio": 85.5
  }
]
```

### 调仓记录 (trades/*.json)

```json
[
  {
    "zh_id": "900304915",
    "trade_date": "2026-03-20",
    "stock_name": "上能电气",
    "stock_code": "300827",
    "trades": 1,
    "position_ratio": "9成以上",
    "position_value": 44.0,
    "direction": "买入",
    "position_change": 20
  }
]
```

## 项目结构

```
dfcfshipan/
├── main.py                      # 入口文件
├── requirements.txt             # 依赖列表
├── proxies.txt                  # 代理列表（可选）
├── src/
│   ├── config.py              # 配置（URL、路径等）
│   ├── spiders/               # 爬虫模块
│   │   ├── base.py            # 基础爬虫类（Playwright 封装）
│   │   ├── player_list.py     # 选手列表爬虫（API）
│   │   ├── player_detail.py   # 选手详情爬虫
│   │   ├── position.py        # 持仓数据爬虫
│   │   └── trade.py           # 调仓记录爬虫
│   ├── storage/                # 存储模块
│   │   └── json_storage.py    # JSON 文件存储
│   ├── analysis/              # 分析模块
│   │   └── position_analyzer.py  # 持仓分析器
│   └── utils/                  # 工具模块
│       ├── logger.py          # 日志配置
│       ├── proxy_pool.py      # 代理池管理
│       └── playwright_manager.py  # Playwright 线程安全管理
└── data/                       # 数据目录（自动创建）
```

## 注意事项

1. **并发数建议 20-30**，过高可能被网站限流
2. **自动重试机制**，Playwright 操作失败会自动重试 3 次
3. **调仓记录需要滚动加载**，爬取较慢
4. **建议使用代理池**避免被封
5. **线程安全**，Playwright 操作使用锁保护，支持多线程并发
6. **断点续传**，默认跳过已存在的选手数据

## 技术说明

### 榜单 API 映射

东方财富网站实际使用的 API 与标签对应关系：

| 榜单标签 | rankType | rateTitle |
|----------|----------|-----------|
| 总榜 | 10004 | 总收益 |
| 年榜 | 10003 | 250日收益 |
| 月榜 | 10001 | 20日收益 |
| 周榜 | 10000 | 5日收益 |
| 日榜 | 10005 | 日收益 |

### Playwright 线程安全

项目使用 `src/utils/playwright_manager.py` 管理 Playwright 实例，通过线程锁确保同时只有一个线程执行 Playwright 操作，避免连接冲突。
