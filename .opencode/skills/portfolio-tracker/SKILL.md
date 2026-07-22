# 大同证券投顾组合追踪器

监控大同证券投顾组合（#413 龙头+情绪ETF双核策略、#278 增强宝1号），识别真实持仓股票并存入 SQLite。

## 用法

```bash
# 一键识别所有组合 + 存入数据库
python scripts/portfolio_monitor.py --identify

# 识别指定组合
python scripts/portfolio_monitor.py --identify --portfolio 413

# 查看数据库摘要
python scripts/portfolio_monitor.py --summary

# 导出组合数据为 JSON
python scripts/portfolio_monitor.py --export 413

# 启动 Web 看板
python scripts/web_dashboard.py --port 5000
```

## 数据流

```
大同证券 API
  ├─ /portfolio/info          → 组合基本信息 + 最新调仓
  ├─ /portfolio/position/list → 持仓明细（代码屏蔽）
  ├─ /portfolio/dealRecord    → 最近 10 条调仓记录
  └─ /portfolio/profit/chart  → 近 6 个月收益走势
         ↓
  多因子评分识别真实股票
    ├─ 分钟K线吻合度 (40分) — 仅限最新买入
    ├─ 当前价吻合度 (60分) — 市值÷持股数
    ├─ 成本价校验 (20分)
    ├─ 昨收校验 (12分)
    └─ 数量验证 (8分)
         ↓
  SQLite (data/portfolio.db)
    ├─ portfolios     组合信息
    ├─ positions      持仓明细
    ├─ trades         调仓记录
    ├─ identified_stocks  识别结果
    └─ profit_chart   收益走势
         ↓
  Web 看板 (Flask)
    └─ http://localhost:5000
```

## Web 看板

启动后访问 http://localhost:5000，顶部导航切换到「投顾组合」：

- **头部**：组合名称、投顾、总资产、总收益
- **指标行**：持仓数 / 调仓数 / 已识别数
- **持仓表**：代码、名称、数量、成本、市值、盈亏、仓位%、备注
  - 高置信识别 → 直接替换股票名称
  - 中低置信 → 代码屏蔽，猜测写入备注列
- **调仓表**：最近 10 条买卖记录
- **走势图**：SVG 双线图（组合 vs 沪深300）

点击右上角「↻ 刷新数据」重新抓取全部组合最新数据。

## 识别策略

持仓识别按置信度分三档：

| 置信度 | 分数 | 前端展示 | 典型场景 |
|--------|------|----------|----------|
| high   | ≥65  | 直接显示股票名 | 分钟K线精确匹配 / 当前价精确匹配 |
| medium | ≥40  | 代码屏蔽+备注列 | 仅价格匹配、ETF均价匹配 |
| low    | <40  | 不保存 | 数据不足 |

## 依赖

```bash
pip install requests mootdx beautifulsoup4 lxml playwright
```

股票行情数据通过 mootdx（通达信数据接口）获取。
