# 东方财富选手 & 大同证券投顾数据 API

提供东方财富实盘大赛选手数据以及大同证券投顾组合持仓/调仓数据的 Web API 服务。

## 项目结构

```
jiarenmens/
├── server.py                          # FastAPI 服务（选手 + 投顾 API）
├── main.py                            # 选手数据爬虫（API-only，rt_get_rank）
├── requirements.txt                   # 依赖列表
├── pyproject.toml
├── config/
│   ├── em_headers.json                # 东方财富 API 请求头
│   └── zhids.txt                      # 选手 ID 列表
├── data/
│   ├── crawl_data.db                  # 选手数据库
│   ├── portfolio.db                   # 投顾组合数据库
│   ├── stock_codes.json               # 股票代码缓存
│   └── checkpoint.json                # 爬取检查点
├── scripts/
│   ├── web_dashboard.py               # Flask 实时看板
│   ├── portfolio_monitor.py           # 投顾组合监控
│   ├── identify_by_close.py           # 收盘价股票识别
│   ├── build_stock_cache.py           # 构建股票代码缓存
│   ├── polldirect.py                  # 直连 API 轮询
│   └── check_positions.py             # DB 检查工具
└── src/
    ├── config.py                      # 配置
    ├── spiders/
    │   └── player_list.py             # 选手列表 API 爬虫
    ├── storage/
    │   ├── interface.py               # 存储接口抽象
    │   ├── sqlite_storage.py          # 选手 SQLite 存储
    │   ├── portfolio_db.py            # 投顾组合 SQLite 存储
    │   └── storage_factory.py         # 存储工厂
    ├── analysis/
    │   └── position_analyzer.py       # 持仓分析
    └── utils/
        └── logger.py                  # 日志配置
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 爬取选手数据

```bash
# 默认爬取（每榜单 500 名）
python main.py

# 测试模式（只处理 10 个选手）
python main.py --test

# 指定每榜单 100 名
python main.py --limit 100
```

### 启动 Web API

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

API 文档: `http://localhost:8000/docs`

### 启动 Web 看板

```bash
python scripts/web_dashboard.py --port 5000 --host 0.0.0.0
```

### 投顾组合监控

```bash
python scripts/portfolio_monitor.py --identify        # 识别股票并存入 DB
python scripts/portfolio_monitor.py --summary          # 查看 DB 摘要
python scripts/portfolio_monitor.py --export 413       # 导出组合 JSON
```

## API 接口

### 东方财富选手数据

| 接口 | 说明 |
|------|------|
| `GET /api/players` | 选手列表（支持排序、分页） |
| `GET /api/players/{zh_id}` | 单个选手详情 |
| `GET /api/players/{zh_id}/positions` | 选手持仓 |
| `GET /api/players/{zh_id}/trades` | 选手调仓记录 |
| `GET /api/players/top-performers` | 当日盈利最高选手 |
| `GET /api/positions/top-holdings` | 持仓最多的股票排行 |
| `GET /api/positions/distribution` | 仓位分布统计 |
| `GET /api/positions/all` | 全部选手持仓 |

### 大同证券投顾数据

| 接口 | 说明 |
|------|------|
| `GET /api/portfolios` | 投顾组合列表 |
| `GET /api/portfolios/{pid}` | 组合概况 |
| `GET /api/portfolios/{pid}/positions` | 组合持仓 |
| `GET /api/portfolios/{pid}/trades` | 组合调仓记录 |
| `GET /api/portfolios/{pid}/identified` | 组合识别结果 |
| `GET /api/portfolios/{pid}/history` | 组合收益走势 |
| `GET /api/portfolios/{pid}/export` | 导出组合完整数据 |

## 技术说明

### 爬虫架构

选手数据纯 API 采集，使用 `rt_get_rank` 榜单接口获取多周期收益率（总榜/年榜/月榜/周榜/日榜），无需浏览器渲染。

### 投顾识别流程

1. `portfolio_monitor.py` 从大同证券 API 获取投顾组合持仓原始数据
2. `identify_by_close.py` 在非交易时段通过收盘价精确匹配股票代码和名称
3. `build_stock_cache.py` 构建全量 A 股代码缓存，用于价格匹配

### 数据存储

- `crawl_data.db` — 选手数据，按 `crawl_date` 字段日隔离
- `portfolio.db` — 投顾组合数据，含持仓/调仓/识别结果/收益历史