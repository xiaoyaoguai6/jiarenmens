"""
选手调仓监控方案
================

## 数据流

1. 定时脚本运行时，从 `followed_players` 表获取关注列表
2. 逐个调用 rtV2 API (`combination_detail_97`) 获取选手最新持仓和调仓
3. 与上次快照对比，检测变动
4. 有变动则生成通知消息，写入通知队列
5. 更新快照

## 存储结构

在 `data/crawl_data.db` 中新增两张表：

### player_snapshots（选手快照）
```
zh_id TEXT PRIMARY KEY,
positions_json TEXT,     -- 当前持仓 JSON 数组
trades_json TEXT,        -- 当前调仓 JSON 数组
snapshot_time TIMESTAMP  -- 快照时间
```

### monitor_alerts（告警队列）
```
id INTEGER PRIMARY KEY AUTOINCREMENT,
zh_id TEXT NOT NULL,
message TEXT NOT NULL,        -- 通知内容
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
sent INTEGER DEFAULT 0       -- 0=未发送 1=已发送
```

## 变动检测逻辑

### 调仓检测
- 当前 trades 与上次 snaphot 的 trades 对比
- 如果出现了新的 `(stock_code + trade_date)` 组合，判定为新增调仓
- 提取：股票名、代码、方向（买入/卖出）、手数、仓位占比变化

### 持仓变动检测
- 对比当前 positions 与上次 snapshot 的 positions
- 新增的股票 → 标记为"新买入"
- 消失的股票 → 标记为"已清仓"
- 仓位比例变化超过 5% → 标记为"加减仓"

## 通知格式

```
📢 选手调仓提醒

选手: 赚钱钱买菜菜
🔄 新买入 深科技(000021)
  买入 2 手，仓位 0% → 39%
  成本价 37.77

📦 当前持仓:
  1. 深科技(000021) 成本37.77 现价39.09 盈亏+3.51% 仓位39%
  2. 大唐电信(600198) 成本8.80 现价6.90 盈亏-21.61% 仓位30%
```

## 运行时间

- A股交易时段：周一至周五 9:30-11:30, 13:00-15:00
- 每 2-4 分钟随机间隔轮询一次
- 轮询间隔在脚本启动时随机生成，每次不同