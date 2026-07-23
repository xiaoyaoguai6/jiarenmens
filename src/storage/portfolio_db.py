"""
组合持仓数据库 (Portfolio Tracker DB)
======================================
存储大同证券投顾组合的持仓、调仓、识别结果。

用法:
  from src.storage.portfolio_db import PortfolioDB
  db = PortfolioDB()
  db.save_snapshot(portfolio_data)
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


DB_PATH = Path(__file__).parent.parent.parent / "data" / "portfolio.db"


def _migrate_remarks(conn):
    """为已有数据库的 positions 表添加 remarks 列（若不存在）"""
    try:
        conn.execute("ALTER TABLE positions ADD COLUMN remarks TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 列已存在，忽略


def _parse_float(val, default=0.0):
    """安全转换浮点数，处理百分比字符串如 '150.59%'"""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = str(val).replace('%', '').replace(',', '').strip()
        return float(s) if s else default
    except (ValueError, TypeError):
        return default


class PortfolioDB:
    def __init__(self, db_path: Path = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self.get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id              INTEGER PRIMARY KEY,
                    name            TEXT,
                    advisor         TEXT,
                    advisor_id      INTEGER,
                    total_assets    REAL,
                    available_cash  REAL,
                    position_value  REAL,
                    total_profit    REAL,
                    daily_profit    REAL,
                    max_drawdown    REAL,
                    total_return    REAL,
                    snapshot_time   TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id    INTEGER NOT NULL,
                    stock_code      TEXT,
                    stock_name      TEXT,
                    market          TEXT,
                    shares          INTEGER,
                    cost_price      REAL,
                    current_price   REAL,
                    cost_amount     REAL,
                    current_value   REAL,
                    profit          REAL,
                    profit_ratio    TEXT,
                    position_date   TEXT,
                    snapshot_time   TEXT,
                    remarks         TEXT DEFAULT '',
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id    INTEGER NOT NULL,
                    stock_code      TEXT,
                    stock_name      TEXT,
                    market          TEXT,
                    direction       TEXT,
                    price           REAL,
                    quantity        INTEGER,
                    amount          REAL,
                    suggest_price   REAL,
                    trade_time      TEXT,
                    price_range     TEXT,
                    cjbh            TEXT,
                    snapshot_time   TEXT,
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS identified_stocks (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id    INTEGER NOT NULL,
                    stock_code      TEXT,
                    stock_name      TEXT,
                    confidence      TEXT,
                    match_price     REAL,
                    buy_price       REAL,
                    match_diff_pct  REAL,
                    score           REAL DEFAULT 0,
                    identified_time TEXT,
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS profit_chart (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id    INTEGER NOT NULL,
                    record_date     TEXT,
                    hs300_value     REAL,
                    asset_value     REAL,
                    snapshot_time   TEXT,
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
                )
            """)

            # Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_pid ON positions(portfolio_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_pid ON trades(portfolio_id)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_dedup ON trades(portfolio_id, trade_time, direction, cjbh)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_identified_pid ON identified_stocks(portfolio_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_profit_pid ON profit_chart(portfolio_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_date ON positions(position_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(trade_time)")

            # 迁移：已有DB的 positions 表添加 remarks 列
            _migrate_remarks(conn)

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---------- Save ----------

    def save_snapshot(self, portfolio_info: Dict, positions: List[Dict],
                      identified: List[Dict] = None,
                      trades: List[Dict] = None,
                      chart_data: Dict = None):
        """保存组合完整快照"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            self._upsert_portfolio(conn, portfolio_info, now)
            pid = portfolio_info.get("portfolio_id") or portfolio_info.get("id")
            self._replace_positions(conn, pid, positions, now)
            if trades:
                for t in trades:
                    self._insert_trade(conn, pid, t, now)
            else:
                # fallback: single trade from portfolio_info
                trade = portfolio_info.get("latest_buy") or portfolio_info.get("portfolioStockRecord")
                if trade:
                    self._insert_trade(conn, pid, trade, now)
            if identified:
                self._save_identified(conn, pid, identified, now)
            if chart_data:
                self._save_profit_chart(conn, pid, chart_data, now)

    def _upsert_portfolio(self, conn, info: Dict, now: str):
        # 兼容两种数据格式: 原始API返回 和 analyze_positions处理后的
        raw = info.get("zczk") or info  # 尝试取原始数据
        zczk = info.get("zczk", {})
        if not zczk:
            zczk = info  # 可能是analyze_positions的扁平结果

        pid = info.get("id") or info.get("portfolio_id")
        name = info.get("name", "")
        advisor_name = (info.get("advisor")
                        or (info.get("advisorUserVO") or {}).get("realName")
                        or "")
        creator_id = info.get("creatorId")

        conn.execute("""
            INSERT OR REPLACE INTO portfolios
            (id, name, advisor, advisor_id, total_assets, available_cash,
             position_value, total_profit, daily_profit, max_drawdown,
             total_return, snapshot_time)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pid,
            name,
            advisor_name,
            creator_id,
            _parse_float(zczk.get("zzc", zczk.get("total_assets", 0))),
            _parse_float(zczk.get("zjye", zczk.get("available_cash", 0))),
            _parse_float(zczk.get("zsz", zczk.get("position_value", 0))),
            _parse_float(zczk.get("zyk", zczk.get("total_profit", 0))),
            _parse_float(zczk.get("zfdyk", zczk.get("daily_profit", 0))),
            _parse_float(zczk.get("maxDrawDown", 0)),
            _parse_float(zczk.get("syl", zczk.get("total_return", 0))),
            now,
        ))

    @staticmethod
    def _parse_shares(pos: Dict) -> int:
        """总持股 = 可用(kysl) + 冻结(djsl)。两者都可能部分屏蔽。"""
        def to_int(v) -> int:
            s = str(v if v is not None else "").replace(",", "").strip()
            if not s or s in ("****", "***", "**.**", "-"):
                return 0
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return 0

        kysl = to_int(pos.get("kysl", 0))
        djsl = to_int(pos.get("djsl", 0))
        gpsl = to_int(pos.get("gpsl", 0))
        # 总持仓优先 kysl+djsl；若都无则回退 gpsl/shares
        total = kysl + djsl
        if total > 0:
            return total
        if gpsl > 0:
            return gpsl
        return to_int(pos.get("shares", 0))

    def _replace_positions(self, conn, pid: int, positions: List[Dict], now: str):
        conn.execute("DELETE FROM positions WHERE portfolio_id = ?", (pid,))
        for pos in positions:
            shares = self._parse_shares(pos)
            try:
                gpsz = float(pos.get("gpsz", "0") or 0)
            except (ValueError, TypeError):
                gpsz = 0.0
            try:
                fdyk = float(pos.get("fdyk", "0") or 0)
            except (ValueError, TypeError):
                fdyk = 0.0
            # 成本价 = (市值 - 盈亏) / 数量
            # 注意: gpmrcb 是历史累计买入总额(含已卖出部分), 不能直接用于计算成本价
            cost_basis = gpsz - fdyk  # 当前持仓的真实成本总额
            cost_price = round(cost_basis / shares, 4) if shares > 0 else 0
            curr_price = round(gpsz / shares, 4) if shares > 0 else 0

            conn.execute("""
                INSERT INTO positions
                (portfolio_id, stock_code, stock_name, market, shares,
                 cost_price, current_price, cost_amount, current_value,
                 profit, profit_ratio, position_date, snapshot_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                pid,
                pos.get("zqdm", ""),
                pos.get("zqmc", ""),
                pos.get("market", ""),
                shares,
                cost_price,
                curr_price,
                cost_basis,        # 改用正确的成本总额, 而非 gpmrcb
                gpsz,
                fdyk,
                pos.get("ykl", ""),
                pos.get("jcrq", ""),
                now,
            ))

    def _insert_trade(self, conn, pid: int, trade: Dict, now: str):
        if isinstance(trade, dict) and "mdate" in trade:
            # 去重: 同组合+同时间+同方向不重复插入
            mdate = trade.get("mdate", "")
            direction = trade.get("mmlb", "")
            cjbh = trade.get("cjbh", "")
            existing = conn.execute(
                "SELECT id FROM trades WHERE portfolio_id=? AND trade_time=? AND direction=? AND cjbh=?",
                (pid, mdate, direction, cjbh)
            ).fetchone()
            if existing:
                return  # 已存在，跳过

            # 处理masked字段 ("***")
            def safe_float(v, default=0.0):
                s = str(v).strip()
                return float(s) if s and s != "***" and s != "**.**" else default
            def safe_int(v, default=0):
                s = str(v).strip()
                return int(s) if s and s != "***" and s != "**.**" else default

            conn.execute("""
                INSERT INTO trades
                (portfolio_id, stock_code, stock_name, market, direction,
                 price, quantity, amount, suggest_price, trade_time,
                 price_range, cjbh, snapshot_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                pid,
                trade.get("zqdm", ""),
                trade.get("zqmc", ""),
                trade.get("scdm", ""),
                direction,
                safe_float(trade.get("cjjg", 0)),
                safe_int(trade.get("cjsl", 0)),
                float(trade.get("cjje", 0)),  # cjje is not masked
                safe_float(trade.get("suggestPrice", 0)),
                mdate,
                trade.get("cwbh", ""),
                cjbh,
                now,
            ))

    def update_position_code(self, pos_id: int, stock_code: str, stock_name: str,
                              remarks: Optional[List[Dict]] = None):
        """更新单个持仓的股票代码、名称和备注。

        当收盘价精确匹配唯一确定时，写入 stock_code 和 stock_name，清除 remarks。
        当多只匹配时，传入 remarks 候选列表，留空 stock_code/stock_name。
        """
        remarks_json = json.dumps(remarks, ensure_ascii=False) if remarks else ""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE positions SET stock_code=?, stock_name=?, remarks=? WHERE id=?",
                (stock_code, stock_name, remarks_json, pos_id)
            )

    def _save_identified(self, conn, pid: int, identified: List[Dict], now: str):
        # 每次全量覆盖该组合识别结果，避免旧识别残留污染
        conn.execute("DELETE FROM identified_stocks WHERE portfolio_id = ?", (pid,))
        for item in identified:
            conn.execute("""
                INSERT INTO identified_stocks
                (portfolio_id, stock_code, stock_name, confidence,
                 match_price, buy_price, match_diff_pct, score, identified_time)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                pid,
                item.get("code", ""),
                item.get("name", ""),
                item.get("confidence", ""),
                item.get("current_price", 0),
                item.get("buy_price", 0),
                item.get("minute_price_match", 0),
                item.get("score", 0),
                now,
            ))

    def _save_profit_chart(self, conn, pid: int, chart: Dict, now: str):
        """保存收益走势数据"""
        dates = chart.get("date", "").split(";")
        hs300 = chart.get("hs300", "").split(";")
        assets = chart.get("assets", "").split(";")
        min_len = min(len(dates), len(hs300), len(assets))
        if min_len == 0:
            return
        # 清除旧的日频数据（同日期不重复插入）
        for i in range(min_len):
            d = dates[i].strip()
            if not d:
                continue
            hs = _parse_float(hs300[i]) if i < len(hs300) else 0
            av = _parse_float(assets[i]) if i < len(assets) else 0
            if d and hs > 0 and av > 0:
                existing = conn.execute(
                    "SELECT id FROM profit_chart WHERE portfolio_id=? AND record_date=?",
                    (pid, d)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE profit_chart SET hs300_value=?, asset_value=?, snapshot_time=? WHERE id=?",
                        (hs, av, now, existing["id"])
                    )
                else:
                    conn.execute(
                        "INSERT INTO profit_chart (portfolio_id, record_date, hs300_value, asset_value, snapshot_time) VALUES (?,?,?,?,?)",
                        (pid, d, hs, av, now)
                    )

    # ---------- Query ----------

    def get_portfolio(self, pid: int) -> Optional[Dict]:
        with self.get_conn() as conn:
            row = conn.execute("SELECT * FROM portfolios WHERE id = ?", (pid,)).fetchone()
            return dict(row) if row else None

    def get_positions(self, pid: int) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE portfolio_id = ? ORDER BY profit DESC", (pid,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_trades(self, pid: int, limit: int = 20) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE portfolio_id = ? ORDER BY trade_time DESC LIMIT ?",
                (pid, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_identified(self, pid: int) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM identified_stocks WHERE portfolio_id = ? ORDER BY id DESC", (pid,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_snapshot_time(self, pid: int) -> Optional[str]:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT snapshot_time FROM portfolios WHERE id = ?", (pid,)
            ).fetchone()
            return row["snapshot_time"] if row else None

    def get_history(self, pid: int, days: int = 30) -> List[Dict]:
        """获取历史收益曲线"""
        with self.get_conn() as conn:
            rows = conn.execute("""
                SELECT record_date, hs300_value, asset_value
                FROM profit_chart
                WHERE portfolio_id = ?
                ORDER BY record_date DESC
                LIMIT ?
            """, (pid, days)).fetchall()
            return [dict(r) for r in rows]

    def export_json(self, pid: int) -> Dict:
        """导出组合完整数据为JSON"""
        return {
            "portfolio": self.get_portfolio(pid),
            "positions": self.get_positions(pid),
            "trades": self.get_trades(pid),
            "identified": self.get_identified(pid),
        }

    def summary(self) -> str:
        """打印所有组合的摘要"""
        with self.get_conn() as conn:
            rows = conn.execute("""
                SELECT p.id, p.name, p.advisor, p.total_assets, p.total_return,
                       p.daily_profit, p.snapshot_time,
                       (SELECT COUNT(*) FROM positions WHERE portfolio_id = p.id) as pos_count,
                       (SELECT COUNT(*) FROM trades WHERE portfolio_id = p.id) as trade_count,
                       (SELECT stock_code || ' ' || stock_name FROM identified_stocks
                        WHERE portfolio_id = p.id ORDER BY id DESC LIMIT 1) as last_identified
                FROM portfolios p
                ORDER BY p.id
            """).fetchall()
            return "\n".join(
                f"  #{r['id']} {r['name']} | {r['advisor']}"
                f" | 总资产:{r['total_assets']:,.2f}"
                f" | 总收益:{r['total_return']:+.2%}"
                f" | 持仓:{r['pos_count']}只 | 调仓:{r['trade_count']}次"
                for r in rows
            ) if rows else "  (空)"