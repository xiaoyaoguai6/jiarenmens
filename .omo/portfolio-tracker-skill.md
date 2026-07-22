---
name: datong-portfolio-tracker
description: Use when tracking 大同证券投顾组合 (portfolio IDs 413, 278). Monitors portfolio API, identifies masked stocks via mootdx minute K-line + real-time prices, stores in SQLite. Supports periodic fetch (5-10min normal / 1min on new buy).
---

# 大同证券投顾组合追踪器

监控大同证券投顾组合的API，检测新买入记录，通过分钟K线+实时股价识别被屏蔽代码的具体股票，结果存入 SQLite。

## 数据源

| 项目 | 说明 |
|------|------|
| 组合API | `https://touguths.dtsbc.com.cn:8066/advisor/busi/h5` |
| 组合 #413 | 龙头+情绪ETF双核策略 (郏西克) |
| 组合 #278 | 增强宝1号 (赵峰) |
| 股票数据 | mootdx (通达信TCP) + akshare (ETF列表) |
| 数据库 | SQLite → `data/portfolio.db` |

## 文件结构

```
jiarenmens/
├── scripts/
│   └── portfolio_monitor.py     # 主监控脚本 (634行)
├── src/
│   └── storage/
│       └── portfolio_db.py      # 数据库模块 (352行)
├── data/
│   ├── portfolio.db             # SQLite 数据库
│   ├── stock_codes.json         # 股票代码缓存
│   └── identified_stocks.json   # 识别结果
└── .omo/
    └── portfolio-tracker-skill.md  # 本文件
```

## 用法命令

### 1. 识别当前持仓 + 存入DB

```bash
cd D:\project\jiarenmens
python scripts/portfolio_monitor.py --identify           # 识别所有组合
python scripts/portfolio_monitor.py --identify --portfolio 413  # 指定组合
```

### 2. 启动持续监控

```bash
python scripts/portfolio_monitor.py
# 无新买入 → 5-10分钟随机间隔
# 检测到新买入 → 1分钟高频模式（最多30轮）
```

### 3. 查看数据库

```bash
python scripts/portfolio_monitor.py --summary            # 数据库摘要
python scripts/portfolio_monitor.py --export 413         # 导出JSON
```

## 数据库表结构

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `portfolios` | 组合基本信息 | id, name, advisor, total_assets, total_return |
| `positions` | 持仓明细 | stock_code, shares, cost_price, current_price, profit, position_date |
| `trades` | 调仓记录 | direction, price, quantity, trade_time |
| `identified_stocks` | 识别结果 | stock_code, stock_name, confidence, match_diff_pct |

## 识别逻辑

```
买入记录(价格P, 时间T, 市场M, 数量Q)
  │
  ├─ 步骤1: 按市场前缀筛选候选股票 (如000***→412只)
  │
  ├─ 步骤2: 用mootdx获取当前股价，过滤±2%内匹配
  │
  └─ 步骤3: 获取买入时间附近分钟K线 → 价格交叉验证
       └─ 匹配度 < 0.5% → 高置信度
       └─ 匹配度 < 2%   → 中置信度
```

## 已识别的持仓（截至2026-07-21）

### 组合 #413 — 龙头+情绪ETF双核策略 (郏西克)

| 代码 | 名称 | 类型 | 买入均价 | 当前价 | 盈亏 |
|------|------|------|---------|-------|------|
| **588170** | 科创半导体ETF华夏 | ETF | 0.9181 | 0.996 | +8.49% |
| **588200** | 科创芯片ETF嘉实 | ETF | 1.2031 | 1.285 | +6.81% |
| **000938** | 紫光股份 | 股票 | 41.31 | 41.46 | +0.35% |

总资产: 2,505,862 元 | 可用资金: 1,672,332 元 | 仓位: 33%

### 组合 #278 — 增强宝1号 (赵峰)

| 代码 | 名称 | 类型 | 买入均价 | 当前价 | 盈亏 |
|------|------|------|---------|-------|------|
| **002*** | (待识别) | 股票 | - | - | -14.53% |
| **603*** | (待识别) | 股票 | - | 43.27? | -20.69% |
| **603*** | (待识别) | 股票 | - | - | -12.49% |
| **300*** | (待识别) | 创业板 | - | - | -6.18% |
| **002*** | (待识别) | 股票 | - | - | -14.34% |
| **300*** | (待识别) | 创业板 | - | - | -19.52% |

总资产: 1,913,240 元 | 总收益: +91.32%

## 依赖安装

```bash
pip install mootdx akshare requests pandas
```

## 定时抓取（服务器配置好后）

### Linux crontab (每10分钟)

```bash
*/10 * * * * cd /path/to/jiarenmens && python scripts/portfolio_monitor.py --identify >> data/cron.log 2>&1
```

### Windows 任务计划

```powershell
# 创建每10分钟执行的任务
$action = New-ScheduledTaskAction -Execute "python" -Argument "D:\project\jiarenmens\scripts\portfolio_monitor.py --identify" -WorkingDirectory "D:\project\jiarenmens"
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00am" -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskName "PortfolioTracker" -Action $action -Trigger $trigger
```

## 注意事项

1. **mootdx 需要国内网络** — 海外服务器可能超时，需代理或VPN
2. **588*** ETF 用 akshare 获取** — mootdx的ETF价格有10倍偏差，akshare数据更准
3. **分钟K线仅交易时段有效** — 非交易时间返回空数据
4. **股票识别有延迟** — 新买入后需等到下一个分钟K线生成才能确认
5. **DB 自动去重** — 同一组合多次运行不会产生重复数据（DELETE+INSERT）
