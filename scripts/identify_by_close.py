"""
收盘价精确匹配 — 在非交易时段通过收盘价精准确定股票代码和名称
===================================================================
核心逻辑：
  1. 收盘后（或非交易时段），API 返回的"当前价"就是当日收盘价，固定的。
  2. 持仓的 unit_price = current_value / shares，应该等于股票收盘价。
  3. 用前缀缩小范围，拿 stock_codes.json 中同前缀的候选股，
     逐一查询腾讯行情获取收盘价，对比 unit_price。
  4. 如果仅一只价格完全一致 → 确定 stock_code + stock_name，写入 DB。
  5. 如果多只价格一致 → 把所有候选写入 remarks 列，下次刷新再缩小范围。
  6. 如果 DB 中已有 remarks（上次不确定的），下次仅跟 remarks 里的候选对比。

用法:
  python scripts/identify_by_close.py --pid 278     # 指定组合
  python scripts/identify_by_close.py --all         # 所有组合
  python scripts/identify_by_close.py --all --force # 强制重新匹配全部
"""

import json
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 项目路径
PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

DATA_DIR = PROJ_ROOT / "data"
STOCK_CODES_FILE = DATA_DIR / "stock_codes.json"
DB_PATH = DATA_DIR / "portfolio.db"


# ── 交易时段判断 ──────────────────────────────────────────────────────────

MARKET_CLOSE_PERIODS = [
    (dtime(0, 0), dtime(9, 15)),        # 盘前（凌晨 ~ 9:15）
    (dtime(11, 30), dtime(13, 0)),       # 午休（11:30 ~ 13:00）
    (dtime(15, 0), dtime(23, 59)),       # 收盘后（15:00 ~ 午夜）
]


def is_market_closed(dt: datetime = None) -> bool:
    """判断当前是否处于非交易时段（收盘价固定的时段）"""
    if dt is None:
        dt = datetime.now()
    t = dt.time()
    # 周末也视为收盘
    if dt.weekday() >= 5:
        return True
    for start, end in MARKET_CLOSE_PERIODS:
        if start <= t <= end:
            return True
    return False


def is_market_open(dt: datetime = None) -> bool:
    """判断当前是否处于盘中交易时段"""
    return not is_market_closed(dt)


# ── 行情查询 ──────────────────────────────────────────────────────────────

def load_stock_codes() -> Dict:
    """加载股票代码缓存"""
    if STOCK_CODES_FILE.exists():
        with open(STOCK_CODES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    print("[WARN] stock_codes.json 不存在，请先运行 build_stock_cache.py")
    return {"stocks": [], "categories": {}}


def get_stocks_by_prefix(prefix: str) -> List[Dict]:
    """根据前缀获取股票列表"""
    cache = load_stock_codes()
    categories = cache.get("categories", {})
    candidates = categories.get(prefix, [])
    if not candidates:
        # 尝试用前3位精确匹配，如果不行尝试前1位
        p3 = prefix[:3]
        if p3 in categories:
            candidates = categories[p3]
        elif prefix[:1] in categories:
            candidates = categories[prefix[:1]]
    return candidates


def get_closing_prices(codes: List[str]) -> Dict[str, float]:
    """
    通过腾讯财经API批量获取当前价（收盘后就是收盘价）。
    返回 {code: price} 映射。
    """
    if not codes:
        return {}
    try:
        import urllib.request
        batch_size = 80
        all_prices = {}

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            try:
                prefixed = []
                for c in batch:
                    if c.startswith(("6", "5", "9")):
                        prefixed.append(f"sh{c}")
                    elif c.startswith("8"):
                        prefixed.append(f"bj{c}")
                    else:
                        prefixed.append(f"sz{c}")

                url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "Mozilla/5.0")
                resp = urllib.request.urlopen(req, timeout=10)
                data = resp.read().decode("gbk")

                for line in data.strip().split(";"):
                    if not line.strip() or "=" not in line or '"' not in line:
                        continue
                    key = line.split("=")[0].split("_")[-1]
                    vals = line.split('"')[1].split("~")
                    if len(vals) < 40:
                        continue
                    code = key[2:] if len(key) > 2 else key
                    price = float(vals[3]) if vals[3] else 0
                    all_prices[code] = price
            except Exception as e:
                print(f"  [WARN] 腾讯行情查询失败 ({batch[0]}...): {e}")
            time.sleep(0.2)

        return all_prices
    except Exception as e:
        print(f"[WARN] 行情查询异常: {e}")
        return {}


def _normalize_etf_price(raw_price: float, unit_price: float) -> float:
    """部分ETF行情返回10倍价格，按单价归一化"""
    if raw_price <= 0 or unit_price <= 0:
        return raw_price
    if raw_price > 5 and unit_price < 5 and raw_price / unit_price > 5:
        scaled = raw_price / 10.0
        if abs(scaled - unit_price) / unit_price < abs(raw_price - unit_price) / unit_price:
            return scaled
    return raw_price


# ── 核心匹配逻辑 ──────────────────────────────────────────────────────────

def find_exact_matches(
    candidates: List[Dict],
    unit_price: float,
    prices: Dict[str, float],
    tolerance: float = 0.001
) -> Tuple[List[Dict], List[Dict]]:
    """
    精确匹配：找出价格与 unit_price 完全一致的候选股票。
    返回: (exact_matches, price_missing)
      - exact_matches: 价格完全匹配的列表
      - price_missing: 未查到行情的候选

    精确匹配规则：
      1. 优先找 exact price == unit_price（浮点容忍 ±0.001）
      2. 如果找不到，放宽到 0.1% 差异
      3. 记录每种匹配级别的结果
    """
    exact_matches = []
    price_missing = []

    for s in candidates:
        code = s["code"]
        if code not in prices:
            price_missing.append(s)
            continue

        raw_px = prices[code]
        px = _normalize_etf_price(raw_px, unit_price)
        if px <= 0:
            continue

        # 精确匹配（浮点容忍）
        if abs(px - unit_price) <= tolerance:
            exact_matches.append({
                "code": code,
                "name": s["name"],
                "price": px,
                "diff": round(abs(px - unit_price), 4),
            })
        # 0.1% 内
        elif unit_price > 0 and abs(px - unit_price) / unit_price <= 0.001:
            exact_matches.append({
                "code": code,
                "name": s["name"],
                "price": px,
                "diff": round(abs(px - unit_price), 4),
            })

    return exact_matches, price_missing


def identify_position_by_closing_price(
    position: Dict,
    prices: Dict[str, float] = None,
    db_remarks: List[Dict] = None
) -> Dict:
    """
    对单个持仓，通过收盘价精确匹配识别股票。

    参数:
      position: 持仓信息（含 stock_code, current_value, shares 等）
      prices:   可选的预加载行情字典（避免重复查询）
      db_remarks: 如果持仓已有 remarks（不确定候选），传入以缩小范围

    返回:
      {
        "identified": True/False,  # 是否最终确定
        "stock_code": "...",       # 确定后的代码（或空）
        "stock_name": "...",       # 确定后的名称（或空）
        "remarks": [...] 或 None,  # 不确定时写入的候选列表
        "match_count": N,          # 匹配到的候选数量
      }
    """
    code_prefix = position.get("stock_code", "")[:3]
    shares = position.get("shares", 0) or 0
    current_value = position.get("current_value", 0) or 0

    if shares <= 0 or current_value <= 0:
        return {
            "identified": False,
            "stock_code": "",
            "stock_name": "",
            "remarks": None,
            "match_count": 0,
            "reason": "shares或current_value无效",
        }

    unit_price = current_value / shares

    # 如果已有 DB remarks，只从 remarks 中的候选进行匹配
    if db_remarks:
        candidates = db_remarks  # 已经是 [{"code":..., "name":...}, ...]
        print(f"    [重匹配] 从 remarks 中 {len(candidates)} 个候选缩小范围...")
    else:
        # 正常走前缀匹配
        candidates = get_stocks_by_prefix(code_prefix)
        if not candidates:
            return {
                "identified": False,
                "stock_code": "",
                "stock_name": "",
                "remarks": None,
                "match_count": 0,
                "reason": f"前缀 {code_prefix} 无候选",
            }

    # 获取行情
    if prices is None:
        codes = [c["code"] for c in candidates]
        all_prices = get_closing_prices(codes)
    else:
        all_prices = prices

    exact_matches, price_missing = find_exact_matches(candidates, unit_price, all_prices)

    if not exact_matches:
        return {
            "identified": False,
            "stock_code": "",
            "stock_name": "",
            "remarks": None,
            "match_count": 0,
            "reason": f"无精确价格匹配 (unit_price={unit_price:.4f})",
        }

    if len(exact_matches) == 1:
        # ✅ 唯一确定
        m = exact_matches[0]
        return {
            "identified": True,
            "stock_code": m["code"],
            "stock_name": m["name"],
            "remarks": None,
            "match_count": 1,
            "price": m["price"],
        }
    else:
        # ❌ 多只股票价格相同（如 ETF 价格相同）
        remarks = [{"code": m["code"], "name": m["name"]} for m in exact_matches]
        return {
            "identified": False,
            "stock_code": "",
            "stock_name": "",
            "remarks": remarks,
            "match_count": len(exact_matches),
            "reason": f"多只匹配 ({len(exact_matches)} 只)",
        }


# ── 批量识别 ──────────────────────────────────────────────────────────────

def identify_portfolio_positions(portfolio_id: int, force: bool = False) -> Dict:
    """
    对一个组合的所有持仓进行收盘价精确匹配。

    参数:
      portfolio_id: 组合ID
      force: 是否强制重新匹配（即使已有 stock_code 也重新匹配）

    返回:
      {
        "portfolio_id": ...,
        "total": N,
        "identified": N,  # 本次新确定的
        "uncertain": N,   # 仍不确定的
        "positions": [...]
      }
    """
    from src.storage.portfolio_db import PortfolioDB

    db = PortfolioDB(DB_PATH)
    positions = db.get_positions(portfolio_id)

    if not positions:
        return {"portfolio_id": portfolio_id, "total": 0,
                "identified": 0, "uncertain": 0, "positions": []}

    print(f"\n{'='*60}")
    print(f"📊 组合 #{portfolio_id} — 收盘价精确匹配")
    print(f"{'='*60}")

    # 收集所有需要查询的候选代码（去重）
    all_need_codes = set()
    pos_need_prices = []  # 记录哪个持仓需要查行情
    for pos in positions:
        code = pos.get("stock_code", "") or ""
        remarks_raw = pos.get("remarks", "") or ""

        # 如果已有完整代码且不强制，跳过
        if code and not code.startswith("*") and not force:
            continue

        shares = pos.get("shares", 0) or 0
        cur_val = pos.get("current_value", 0) or 0
        if shares <= 0 or cur_val <= 0:
            continue

        # 已有 remarks 则只从 remarks 中取候选
        if remarks_raw:
            try:
                remarks_candidates = json.loads(remarks_raw) if isinstance(remarks_raw, str) else remarks_raw
            except (json.JSONDecodeError, TypeError):
                remarks_candidates = []
            if remarks_candidates:
                for c in remarks_candidates:
                    all_need_codes.add(c["code"])
                pos_need_prices.append((pos, remarks_candidates))
                continue

        # 正常前缀匹配
        prefix = code[:3] if code else ""
        if not prefix or not prefix.isdigit():
            continue
        candidates = get_stocks_by_prefix(prefix)
        for c in candidates:
            all_need_codes.add(c["code"])
        pos_need_prices.append((pos, None))

    # 批量查询行情
    print(f"  查询 {len(all_need_codes)} 只候选股票行情...")
    all_prices = get_closing_prices(list(all_need_codes)) if all_need_codes else {}
    print(f"  获取到 {len(all_prices)} 只行情数据")

    # 逐条匹配
    new_identified = 0
    uncertain_count = 0
    results = []

    for pos, remarks_candidates in pos_need_prices:
        pos_id = pos.get("id")
        mask = pos.get("stock_code", "")
        shares = pos.get("shares", 0) or 0
        cur_val = pos.get("current_value", 0) or 0
        unit_price = cur_val / shares if shares > 0 else 0

        print(f"\n  [持仓] {mask} 单价≈{unit_price:.4f} 市值={cur_val:.0f} 数量={shares}")

        result = identify_position_by_closing_price(pos, all_prices, remarks_candidates)

        if result["identified"]:
            print(f"    ✅ 确定: {result['stock_code']} {result['stock_name']} (价格={result.get('price',0):.2f})")
            # 写入 DB
            db.update_position_code(pos_id, result["stock_code"], result["stock_name"], remarks=None)
            new_identified += 1
        elif result["remarks"]:
            print(f"    ⚠️ 不确定: {result['match_count']} 只价格相同")
            for r in result["remarks"]:
                print(f"      候选: {r['code']} {r['name']}")
            # 写入 remarks
            db.update_position_code(pos_id, "", "", remarks=result["remarks"])
            uncertain_count += 1
        else:
            print(f"    ❌ {result.get('reason', '无匹配')}")

        results.append(result)

    print(f"\n{'='*60}")
    print(f"  合计: {len(pos_need_prices)} 待识别 → 新确定 {new_identified}, 仍不确定 {uncertain_count}")
    print(f"{'='*60}")

    return {
        "portfolio_id": portfolio_id,
        "total": len(pos_need_prices),
        "identified": new_identified,
        "uncertain": uncertain_count,
        "results": results,
    }


# ── 主入口 ────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="收盘价精确匹配股票识别")
    parser.add_argument("--pid", type=int, help="组合ID（如 278）")
    parser.add_argument("--all", action="store_true", help="所有组合")
    parser.add_argument("--force", action="store_true", help="强制重新匹配")
    args = parser.parse_args()

    # 检查是否在非交易时段
    if not args.force and is_market_open():
        print(f"[WARN] 当前是盘中交易时段，收盘价尚未固定！")
        print(f"       建议在以下时段运行: 凌晨~9:15, 11:30~13:00, 15:00后")
        print(f"       使用 --force 可强制运行（但不推荐）")
        return

    if args.pid:
        identify_portfolio_positions(args.pid, force=args.force)
    elif args.all:
        from src.storage.portfolio_db import PortfolioDB
        db = PortfolioDB(DB_PATH)
        with db.get_conn() as conn:
            rows = conn.execute("SELECT id FROM portfolios").fetchall()
        for row in rows:
            identify_portfolio_positions(row["id"], force=args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()