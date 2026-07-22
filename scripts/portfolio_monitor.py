"""
组合持仓监控 + 股票识别系统
==============================
监控大同证券投顾组合API，检测新的买入记录，通过分钟K线+实时价格识别具体股票。
结果自动存入 SQLite 数据库，支持定时抓取。

用法:
  python scripts/portfolio_monitor.py                          # 启动监控模式
  python scripts/portfolio_monitor.py --identify               # 识别+存DB
  python scripts/portfolio_monitor.py --identify --portfolio 278  # 指定组合
  python scripts/portfolio_monitor.py --summary                # 查看DB摘要
  python scripts/portfolio_monitor.py --export 413             # 导出JSON
"""

import requests
import json
import time
import random
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# 本地缓存目录
CACHE_DIR = Path(__file__).parent.parent / 'data'
CACHE_DIR.mkdir(exist_ok=True)
STOCK_CODES_FILE = CACHE_DIR / 'stock_codes.json'
STATE_FILE = CACHE_DIR / 'portfolio_state.json'
RESULTS_FILE = CACHE_DIR / 'identified_stocks.json'

# 组合API地址
BASE_URL = "https://touguths.dtsbc.com.cn:8066/advisor/busi/h5"
PORTFOLIOS = {
    413: {"name": "龙头+情绪ETF双核策略", "advisor": "郏西克"},
    278: {"name": "增强宝1号", "advisor": "赵峰"},
}

# 数据库
DB_PATH = CACHE_DIR / "portfolio.db"

# ===================== API 数据获取 =====================

def fetch_portfolio_info(portfolio_id: int) -> Optional[Dict]:
    """获取组合详情，包括最新调仓记录"""
    try:
        resp = requests.get(
            f"{BASE_URL}/portfolio/info?id={portfolio_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("flag") == 0 and data.get("data"):
                return data["data"]
        return None
    except Exception as e:
        print(f"  [ERROR] fetch portfolio info failed: {e}")
        return None

def fetch_position_list(portfolio_id: int) -> Optional[List]:
    """获取持仓明细列表"""
    try:
        resp = requests.get(
            f"{BASE_URL}/portfolio/position/list?id={portfolio_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("flag") == 0 and data.get("data"):
                return data["data"]
        return None
    except Exception as e:
        print(f"  [ERROR] fetch position list failed: {e}")
        return None

def fetch_deal_records(portfolio_id: int, page: int = 0, size: int = 10) -> Optional[List]:
    """获取调仓记录列表（最近N条）"""
    try:
        resp = requests.get(
            f"{BASE_URL}/portfolio/dealRecord?portfolioId={portfolio_id}&page={page}&size={size}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("flag") == 0 and data.get("data"):
                return data["data"].get("content", [])
        return None
    except Exception as e:
        print(f"  [ERROR] fetch deal records failed: {e}")
        return None

def fetch_profit_chart(portfolio_id: int) -> Optional[Dict]:
    """获取收益走势数据（含沪深300对比）"""
    try:
        resp = requests.get(
            f"{BASE_URL}/portfolio/profit/chart?id={portfolio_id}&queryType=2",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("flag") == 0 and data.get("data"):
                return data["data"]
        return None
    except Exception as e:
        print(f"  [ERROR] fetch profit chart failed: {e}")
        return None


# ===================== 股票数据获取 =====================

def load_stock_codes() -> Dict:
    """加载股票代码缓存"""
    if STOCK_CODES_FILE.exists():
        with open(STOCK_CODES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    print("[WARN] Stock codes cache not found, building now...")
    os.system(f'python "{CACHE_DIR / "build_stock_cache.py"}"')
    if STOCK_CODES_FILE.exists():
        with open(STOCK_CODES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"stocks": [], "categories": {}}

def get_stocks_by_prefix(prefix: str) -> List[Dict]:
    """根据前缀获取股票列表"""
    cache = load_stock_codes()
    categories = cache.get("categories", {})
    return categories.get(prefix, [])

def get_current_prices(codes: List[str]) -> Dict[str, float]:
    """通过mootdx批量获取当前股价"""
    if not codes:
        return {}
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std')

        # 分批查询，每批最多50个
        batch_size = 50
        all_prices = {}

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            try:
                result = client.quotes(symbol=batch)
                if result is not None and len(result) > 0:
                    for _, row in result.iterrows():
                        code = str(row.get('code', ''))
                        price = row.get('price', 0)
                        vol = row.get('vol', 0)
                        last_close = row.get('last_close', 0)
                        open_price = row.get('open', 0)
                        high = row.get('high', 0)
                        low = row.get('low', 0)
                        all_prices[code] = {
                            'price': float(price),
                            'open': float(open_price),
                            'high': float(high),
                            'low': float(low),
                            'last_close': float(last_close),
                            'vol': int(vol),
                        }
            except Exception as e:
                print(f"  [WARN] batch query failed for {batch[0]}...: {e}")
            time.sleep(0.3)  # 避免请求过快

        return all_prices
    except ImportError:
        print("[WARN] mootdx not installed. Install with: pip install mootdx")
        return {}
    except Exception as e:
        print(f"[WARN] mootdx query failed: {e}")
        return {}

def get_minute_kline(code: str, date: str) -> Optional[List]:
    """获取分钟的K线数据"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std')
        # 判断市场: 0=深圳, 1=上海
        if code.startswith('6') or code.startswith('5') or code.startswith('58'):
            mk = 1
        elif code.startswith('9'):
            mk = 1  # 北交所
        else:
            mk = 0

        result = client.minutes(symbol=code, date=date)
        if result is not None and len(result) > 0:
            data = []
            for _, row in result.iterrows():
                data.append({
                    'price': float(row.get('price', 0)),
                    'vol': int(row.get('vol', 0)),
                    'volume': int(row.get('volume', 0)),
                })
            return data
        return None
    except Exception as e:
        print(f"  [WARN] minute kline failed for {code}: {e}")
        return None

# ===================== 持仓数据分析 =====================

def analyze_positions(portfolio_id: int) -> Dict:
    """分析组合的持仓，计算关键信息"""
    info = fetch_portfolio_info(portfolio_id)
    positions = fetch_position_list(portfolio_id)

    if not info:
        return {"error": f"Failed to fetch portfolio {portfolio_id}"}

    result = {
        "portfolio_id": portfolio_id,
        "name": info.get("name"),
        "advisor": info.get("advisorUserVO", {}).get("realName"),
        "total_assets": info.get("zczk", {}).get("zzc"),
        "total_profit": info.get("totalProfit"),
        "positions": [],
        "latest_buy": None,
    }

    # 处理最新调仓记录
    record = info.get("portfolioStockRecord")
    if record:
        # 买入记录中的zqdm可能是"****"完全屏蔽，需要从持仓中匹配
        buy_market = record.get("scdm", "")
        buy_price = float(record.get("cjjg", 0))
        buy_qty = int(record.get("cjsl", 0))
        buy_code_masked = record.get("zqdm", "****")

        # 从持仓中匹配对应股票的前缀
        matched_prefix = buy_code_masked[:3] if buy_code_masked != "****" else "???"
        if positions and (buy_code_masked == "****" or not buy_code_masked):
            # 尝试通过价格和市场匹配
            for pos in positions:
                pos_djsl = int(pos.get("djsl", "0"))
                pos_gpsz = float(pos.get("gpsz", "0") or 0)
                pos_gpmrcb = float(pos.get("gpmrcb", "0") or 0)

                # 如果持有数量和买入数量一致，且市场匹配
                market_match = (buy_market in pos.get("market", "")) if buy_market else True

                # 估算单价
                if pos_djsl > 0 and pos_gpmrcb > 0:
                    est_price = pos_gpmrcb / pos_djsl
                    price_diff = abs(est_price - buy_price) / buy_price
                    if price_diff < 0.02 and market_match:
                        matched_prefix = pos.get("zqdm", "???")[:3]
                        break

                # 如果买入后持仓数量=买入数量（全新买入，非补仓）
                if pos_djsl == buy_qty and market_match:
                    matched_prefix = pos.get("zqdm", "???")[:3]
                    break

        if matched_prefix == "???" and positions:
            # 最后手段：从持仓中提取所有不同的前缀，用市场来缩小范围
            market_prefix_map = {"上海A股": ["600", "601", "603", "605", "588"],
                                 "深圳A股": ["000", "001", "002", "003"],
                                 "创业板": ["300", "301"]}
            possible_prefixes = market_prefix_map.get(buy_market, [])
            for pos in positions:
                pos_prefix = pos.get("zqdm", "")[:3]
                if pos_prefix in possible_prefixes:
                    matched_prefix = pos_prefix
                    break

        result["latest_buy"] = {
            "stock_code_prefix": matched_prefix + "***",
            "stock_name": record.get("zqmc", "****"),
            "market": buy_market,
            "buy_time": record.get("mdate"),
            "buy_price": buy_price,
            "buy_quantity": buy_qty,
            "buy_amount": float(record.get("cjje", 0)),
            "suggest_price": float(record.get("suggestPrice", 0)),
            "direction": record.get("mmlb"),
            "price_range": record.get("cwbh"),
        }

    # 处理持仓
    if positions:
        for pos in positions:
            zqdm = pos.get("zqdm", "")
            gpsl_str = pos.get("gpsl", "0")
            # gpsl might be mask "****", so extract from gpmrcb and gp cb
            gpmrcb_str = pos.get("gpmrcb", "0")
            gpsz_str = pos.get("gpsz", "0")
            djsl = int(pos.get("djsl", "0"))  # 冻结数量

            # 计算实际持仓
            gpmrcb = float(gpmrcb_str) if gpmrcb_str.replace('.', '').replace('-', '').isdigit() else 0
            gpsz = float(gpsz_str) if gpsz_str.replace('.', '').replace('-', '').isdigit() else 0

            position_info = {
                "code_prefix": zqdm[:3] + "***",
                "full_code_masked": zqdm,
                "market": pos.get("market"),
                "cost_amount": gpmrcb,
                "current_value": gpsz,
                "profit": float(pos.get("fdyk", 0)) if pos.get("fdyk", "**").replace('.', '').replace('-', '').isdigit() else 0,
                "profit_ratio": pos.get("ykl", "0%"),
                "frozen_shares": djsl,
            }

            # 计算均价
            if gpmrcb > 0 and djsl > 0:
                position_info["estimated_cost_price"] = round(gpmrcb / djsl, 2)

            result["positions"].append(position_info)

    return result

def _normalize_quote_price(raw_price: float, target_price: float) -> float:
    """mootdx 对部分 ETF(588/51x/159) 返回 10x 价格，按目标价归一化。"""
    if raw_price <= 0 or target_price <= 0:
        return raw_price
    # 若行情价明显是目标价的 ~10 倍，则缩回
    if raw_price > 5 and target_price < 5 and raw_price / target_price > 5:
        scaled = raw_price / 10.0
        if abs(scaled - target_price) / target_price < abs(raw_price - target_price) / target_price:
            return scaled
    return raw_price


def filter_candidates_by_price(candidates: List[Dict], target_price: float, threshold: float = 0.02) -> List[Dict]:
    """按价格筛选候选股票"""
    codes = [s["code"] for s in candidates]
    prices = get_current_prices(codes)

    # 按当前价格与目标价格的差异排序
    matches = []
    for s in candidates:
        code = s["code"]
        name = s["name"]
        if code in prices:
            raw = prices[code]["price"]
            current_price = _normalize_quote_price(raw, target_price)
            if current_price <= 0 or target_price <= 0:
                continue
            diff_pct = abs(current_price - target_price) / target_price
            if diff_pct <= threshold:
                data = dict(prices[code])
                data["price"] = current_price
                # 同步归一化 high/low/last_close，便于后续评分
                for k in ("high", "low", "last_close", "open"):
                    if data.get(k):
                        data[k] = _normalize_quote_price(float(data[k]), target_price)
                matches.append({
                    "code": code,
                    "name": name,
                    "current_price": current_price,
                    "diff_pct": round(diff_pct * 100, 2),
                    "data": data,
                })

    # 按差异排序
    matches.sort(key=lambda x: x["diff_pct"])
    return matches

def score_candidates(confirmed: List[Dict], buy_price: float,
                    buy_qty: int, buy_amount: float) -> List[Dict]:
    """多因子评分：综合分钟K线、当前价格、成交量、价格区间锁定最优匹配"""
    scored = []
    for c in confirmed:
        score = 0.0
        details = []

        # 因子1: 分钟K线买入时刻价格吻合度 (0-40分)
        nd = c.get("nearby_diff_pct", 999)
        if nd <= 0.3:
            score += 40; details.append(f"K线精确+{40}")
        elif nd <= 0.5:
            score += 36; details.append(f"K线高+{36}")
        elif nd <= 1.0:
            score += 30; details.append(f"K线中+{30}")
        elif nd <= 2.0:
            score += 20; details.append(f"K线低+{20}")
        elif nd <= 5.0:
            score += 10; details.append(f"K线弱+{10}")
        else:
            details.append("K线无+0")

        # 因子2: 当前价与买入价吻合度 (0-30分)
        cd = c.get("diff_pct", 999)
        if cd <= 0.3:
            score += 30; details.append(f"当前价精确+{30}")
        elif cd <= 0.5:
            score += 27; details.append(f"当前价高+{27}")
        elif cd <= 1.0:
            score += 22; details.append(f"当前价中+{22}")
        elif cd <= 2.0:
            score += 15; details.append(f"当前价低+{15}")
        elif cd <= 5.0:
            score += 8; details.append(f"当前价弱+{8}")
        else:
            details.append("当前价无+0")

        # 因子3: 金额吻合度 (0-20分)
        # 买入金额 ≈ 当前价 × 买入数量，看是否与API返回的买入金额匹配
        cur_price = c.get("current_price", 0)
        if cur_price > 0 and buy_qty > 0 and buy_amount > 0:
            est_amount = cur_price * buy_qty
            amt_diff = abs(est_amount - buy_amount) / buy_amount
            if amt_diff <= 0.01:
                score += 20; details.append(f"金额精确+{20}")
            elif amt_diff <= 0.03:
                score += 15; details.append(f"金额高+{15}")
            elif amt_diff <= 0.05:
                score += 10; details.append(f"金额中+{10}")
            elif amt_diff <= 0.10:
                score += 5; details.append(f"金额低+{5}")
            else:
                details.append("金额差+0")
        else:
            details.append("金额无+0")

        # 因子4: 当日价格区间合理性 (0-10分)
        data = c.get("data", {})
        high = data.get("high", 0)
        low = data.get("low", 0)
        last_close = data.get("last_close", 0)
        if high > 0 and low > 0 and buy_price > 0:
            if low <= buy_price <= high:
                score += 10; details.append("区间内含+10")
            else:
                mid = (high + low) / 2
                if abs(buy_price - mid) / mid <= 0.03:
                    score += 5; details.append("区间附近+5")
                else:
                    details.append("区间外+0")
        if last_close > 0 and buy_price > 0:
            lc_diff = abs(buy_price - last_close) / last_close
            if lc_diff <= 0.01:
                score += 3; details.append("昨收吻合+3")
            elif lc_diff <= 0.03:
                score += 1; details.append("昨收近+1")

        c["score"] = round(score, 1)
        c["score_details"] = " | ".join(details)
        scored.append(c)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def identify_stock_by_buy(portfolio_id: int, portfolio_info: Dict = None) -> Optional[Dict]:
    """根据买入记录识别具体股票"""
    if not portfolio_info:
        portfolio_info = analyze_positions(portfolio_id)

    if "error" in portfolio_info:
        print(f"  [ERROR] {portfolio_info['error']}")
        return None

    latest_buy = portfolio_info.get("latest_buy")
    if not latest_buy:
        print(f"  [INFO] No buy record found for portfolio #{portfolio_id}")
        return None

    print(f"\n{'='*60}")
    print(f"组合 #{portfolio_id}: {portfolio_info['name']}")
    print(f"投顾: {portfolio_info['advisor']}")
    print(f"{'='*60}")

    print(f"\n最新买入记录:")
    print(f"  代码: {latest_buy['stock_code_prefix']}")
    print(f"  市场: {latest_buy['market']}")
    print(f"  时间: {latest_buy['buy_time']}")
    print(f"  价格: {latest_buy['buy_price']} 元")
    print(f"  数量: {latest_buy['buy_quantity']} 股")
    print(f"  金额: {latest_buy['buy_amount']:.2f} 元")
    print(f"  建议价: {latest_buy['suggest_price']} 元")

    # 保存完整信息到DB（不管识别成功与否都保存原始数据）
    all_positions = fetch_position_list(portfolio_id)
    raw_info = fetch_portfolio_info(portfolio_id)  # 原始API数据
    save_to_db(raw_info or portfolio_info, all_positions or [])

    # 获取代码前缀
    code_prefix = latest_buy['stock_code_prefix'][:3]
    buy_price = latest_buy['buy_price']
    suggest_price = latest_buy['suggest_price']
    buy_time = latest_buy['buy_time']
    buy_date = buy_time.split(" ")[0] if " " in buy_time else ""

    # 获取候选股票
    candidates = get_stocks_by_prefix(code_prefix)
    if not candidates:
        print(f"\n  [WARN] 没有找到{code_prefix}***前缀的股票")
        return None

    print(f"\n候选范围: {code_prefix}*** ({len(candidates)}只候选)")

    # 1. 先用当前价格筛选 (threshold 2%)
    print(f"\n[步骤1] 按当前价格 ≈ {buy_price} 元筛选(±2%):")
    matches = filter_candidates_by_price(candidates, buy_price, threshold=0.02)

    if not matches:
        print(f"  没有找到当前价格接近的股票，放宽阈值到5%...")
        matches = filter_candidates_by_price(candidates, buy_price, threshold=0.05)

    if matches:
        print(f"  找到 {len(matches)} 只价格匹配的股票:")
        for m in matches[:15]:
            marker = " *" if m["diff_pct"] < 1 else ""
            print(f"    {m['code']} {m['name']} - 当前价: {m['current_price']:.2f} (差异: {m['diff_pct']}%){marker}")
        if len(matches) > 15:
            print(f"    ... 还有 {len(matches)-15} 只")
    else:
        print(f"  没有找到当前价格接近的股票")
        # 获取所有候选的当前价格，看看整体价格分布
        codes = [s["code"] for s in candidates[:50]]
        prices = get_current_prices(codes)
        if prices:
            price_range = [v["price"] for v in prices.values() if v["price"] > 0]
            if price_range:
                print(f"  前50只候选价格范围: {min(price_range):.2f} ~ {max(price_range):.2f}")
        return None

    # 2. 如果有买入日期，用分钟K线在买入时间附近确认
    if buy_date and matches:
        # 转换日期格式: YYYY-MM-DD -> YYYYMMDD
        kline_date = buy_date.replace("-", "")
        print(f"\n[步骤2] 检查买入时间({buy_time})附近的分钟K线...")
        confirmed = []
        for m in matches[:20]:  # 只检查前20只
            kline = get_minute_kline(m["code"], kline_date)
            if kline:
                # 查找买入时间附近的K线
                buy_hour_min = buy_time.split(" ")[1] if " " in buy_time else "09:30:00"
                buy_hour, buy_min = map(int, buy_hour_min.split(":")[:2])

                # 分钟数据索引: 9:30=索引0, 每1分钟一个, 中午休市(11:30-13:00)跳过
                morning_minutes = (11 - 9) * 60 + 30 - 30  # 9:30到11:30 = 120分钟
                if buy_hour < 12:
                    time_idx = (buy_hour - 9) * 60 + buy_min - 30
                else:
                    # 下午: 从13:00开始, 索引120
                    afternoon_offset = (buy_hour - 13) * 60 + buy_min
                    time_idx = morning_minutes + afternoon_offset
                if 0 <= time_idx < len(kline):
                    nearby_price = kline[time_idx]["price"]
                    price_diff = abs(nearby_price - buy_price) / buy_price
                    m["nearby_minute_price"] = nearby_price
                    m["buy_time_idx"] = time_idx
                    m["nearby_diff_pct"] = round(price_diff * 100, 2)

                    if price_diff < 0.005:  # 0.5% 以内
                        confirmed.append(m)
                        print(f"  [OK] {m['code']} {m['name']}: 分钟价={nearby_price:.2f} (差异{price_diff*100:.2f}%) ** 高度匹配")
                    elif price_diff < 0.02:
                        confirmed.append(m)
                        print(f"  [~] {m['code']} {m['name']}: 分钟价={nearby_price:.2f} (差异{price_diff*100:.2f}%)")
                else:
                    print(f"  ? {m['code']} {m['name']}: 时间索引{time_idx}超出范围(0-{len(kline)-1})")

        if confirmed:
            # 多因子评分排序
            scored = score_candidates(confirmed, buy_price,
                                      latest_buy.get('buy_quantity', 0),
                                      latest_buy.get('buy_amount', 0))

            print(f"\n{'='*60}")
            print(f"** 多因子评分识别结果 **")
            print(f"{'='*60}")
            for i, c in enumerate(scored):
                if i == 0 and c["score"] >= 70:
                    label = "★ 首选 (高置信)"
                elif i == 0:
                    label = "首选"
                elif i == 1 and c["score"] >= 50:
                    label = "备选"
                else:
                    continue  # 只展示前2个
                print(f"  [{label}] {c['code']} {c['name']}")
                print(f"    综合评分: {c['score']}/100")
                print(f"    当前价: {c['current_price']:.2f}  分钟价: {c.get('nearby_minute_price', 0):.2f}")
                print(f"    K线差异: {c.get('nearby_diff_pct', 99):.2f}%  当前差异: {c.get('diff_pct', 99):.2f}%")
                print(f"    评分明细: {c.get('score_details', '')}")

            # 只保留最佳匹配
            best = scored[0]
            top_results = [best]

            # 如果第二名分数也很高（>= 70），保留作为备选
            if len(scored) > 1 and scored[1]["score"] >= 70:
                top_results.append(scored[1])
            elif len(scored) > 1 and scored[1]["score"] >= 50:
                # 中置信备选
                top_results.append(scored[1])

            # 置信度判定
            def get_confidence(s):
                if s >= 85: return "high"
                if s >= 65: return "high"
                if s >= 50: return "medium"
                return "low"

            result = {
                "portfolio_id": portfolio_id,
                "portfolio_name": portfolio_info["name"],
                "advisor": portfolio_info["advisor"],
                "buy_record": latest_buy,
                "identified_stocks": [
                    {
                        "code": c["code"],
                        "name": c["name"],
                        "current_price": c["current_price"],
                        "confidence": get_confidence(c["score"]),
                        "score": c["score"],
                        "minute_price_match": c.get("nearby_diff_pct"),
                    }
                    for c in top_results
                ]
            }
            return result
        else:
            print(f"\n  [INFO] 分钟K线未确认到高度匹配的股票")

    # 3. 如果只有价格匹配但没有分钟K线确认
    if matches:
        # 对纯价格匹配用简化的三因子评分
        price_only_scored = score_candidates(
            [dict(m, nearby_diff_pct=999) for m in matches],
            buy_price,
            latest_buy.get('buy_quantity', 0),
            latest_buy.get('buy_amount', 0)
        )
        best = price_only_scored[0]
        print(f"\n{'='*60}")
        print(f"** 最佳猜测(仅价格匹配 - 评分 {best['score']}/100) **")
        print(f"{'='*60}")
        print(f"  {best['code']} {best['name']}")
        print(f"    当前价: {best['current_price']:.2f}  差异: {best['diff_pct']:.2f}%")
        conf = "high" if best["score"] >= 65 else ("medium" if best["score"] >= 50 else "low")
        result = {
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio_info["name"],
            "advisor": portfolio_info["advisor"],
            "buy_record": latest_buy,
            "identified_stocks": [{
                "code": best["code"],
                "name": best["name"],
                "current_price": best["current_price"],
                "confidence": conf,
                "score": best["score"],
                "minute_price_match": None,
            }],
        }
        return result

    return None


def identify_existing_positions(portfolio_id: int, positions: List[Dict],
                                identified: List[Dict]) -> List[Dict]:
    """对存量持仓逐条识别。同前缀多持仓各自按单价匹配。"""
    already_codes = set(i.get("code", i.get("stock_code", "")) for i in identified)

    new_identified = []
    def _to_int(v) -> int:
        s = str(v if v is not None else "").replace(",", "").strip()
        if not s or s in ("****", "***", "**.**", "-"):
            return 0
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    for pos in positions:
        code = pos.get("zqdm") or pos.get("stock_code") or ""
        prefix = code[:3]
        if not prefix or not prefix.isdigit():
            continue

        # 总持股 = 可用 + 冻结
        kysl = _to_int(pos.get("kysl", 0))
        djsl = _to_int(pos.get("djsl", 0))
        gpsl = _to_int(pos.get("gpsl", 0))
        shares = (kysl + djsl) if (kysl + djsl) > 0 else (gpsl or _to_int(pos.get("shares", 0)))
        if shares <= 0:
            continue

        # Parse current value
        cur_val = 0.0
        for f in ["gpsz", "current_value"]:
            v = pos.get(f, 0)
            try:
                cur_val = float(v)
                if cur_val > 0:
                    break
            except (ValueError, TypeError):
                continue
        if cur_val <= 0:
            continue

        unit_price = cur_val / shares

        # Parse cost amount
        cost_amount = 0.0
        for f in ["gpmrcb", "cost_amount"]:
            v = pos.get(f, 0)
            try:
                cost_amount = float(v)
                if cost_amount > 0:
                    break
            except (ValueError, TypeError):
                continue
        cost_price = cost_amount / shares if shares > 0 and cost_amount > 0 else 0

        print(f"\n  [存量识别] {prefix}*** 单价≈{unit_price:.4f} 成本价≈{cost_price:.4f} 市值={cur_val:.0f} 数量={shares}")

        # Get candidates
        candidates = get_stocks_by_prefix(prefix)
        if not candidates:
            print(f"    [WARN] 没有找到{prefix}***前缀的股票")
            continue

        # Filter by price proximity
        codes = [s["code"] for s in candidates]
        prices = get_current_prices(codes)
        if not prices:
            continue

        scored = []
        for s in candidates:
            sc = s["code"]
            if sc not in prices:
                continue
            pdata = prices[sc]
            cur_px = pdata["price"]
            if cur_px <= 0:
                continue

            # Normalize ETF prices (mootdx qoutes return 10x for ETF/指数)
            if cur_px > 5 and unit_price < 5 and cur_px / unit_price > 5:
                norm = cur_px / 10.0
                if abs(norm - unit_price) / unit_price < abs(cur_px - unit_price) / unit_price:
                    cur_px = norm

            diff_pct = abs(cur_px - unit_price) / unit_price * 100
            if diff_pct > 20:
                continue  # skip >20% deviation

            score = 0.0
            details = []

            # 因子1: 当前价吻合度 (0-60) —— 市值÷持股=真实单价，高度可信
            if diff_pct <= 0.2:
                score += 60; details.append("价格精确+60")
            elif diff_pct <= 0.5:
                score += 55; details.append("价格高+55")
            elif diff_pct <= 1.0:
                score += 45; details.append("价格中+45")
            elif diff_pct <= 2.0:
                score += 30; details.append("价格低+30")
            elif diff_pct <= 5.0:
                score += 15; details.append("价格弱+15")
            else:
                score += 5; details.append("价格微+5")

            # 因子2: 成本价辅助校验 (0-20)
            if cost_price > 0:
                cost_diff = abs(cur_px - cost_price) / cost_price * 100
                if cost_diff <= 0.5:
                    score += 20; details.append("成本吻合+20")
                elif cost_diff <= 1.0:
                    score += 16; details.append("成本近+16")
                elif cost_diff <= 2.0:
                    score += 10; details.append("成本中+10")
                elif cost_diff <= 5.0:
                    score += 5; details.append("成本低+5")

            # 因子3: 昨收校验 (0-12)
            last_close = pdata.get("last_close", 0)
            if last_close > 0:
                lc_diff = abs(cur_px - last_close) / last_close * 100
                if lc_diff <= 0.3:
                    score += 12; details.append("昨收精确+12")
                elif lc_diff <= 0.5:
                    score += 10; details.append("昨收高+10")
                elif lc_diff <= 1.0:
                    score += 7; details.append("昨收中+7")
                elif lc_diff <= 2.0:
                    score += 4; details.append("昨收低+4")

            # 因子4: 数量验证 (0-8)
            vol = pdata.get("vol", 0)
            if vol > 0 and cur_val > 0:
                estimated_shares = cur_val / cur_px
                if shares > 0:
                    qty_diff = abs(estimated_shares - shares) / shares
                    if qty_diff <= 0.01:
                        score += 8; details.append("数量精确+8")
                    elif qty_diff <= 0.05:
                        score += 4; details.append("数量近+4")

            if score >= 20:  # Only keep if at least some match
                scored.append({
                    "code": sc,
                    "name": s["name"],
                    "current_price": cur_px,
                    "diff_pct": round(diff_pct, 2),
                    "score": round(score, 1),
                    "score_details": " | ".join(details),
                })

        if scored:
            scored.sort(key=lambda x: x["score"], reverse=True)
            best = None
            for cand in scored:
                # 避免同一代码重复加入；同前缀不同持仓可匹配不同代码
                if cand["code"] not in already_codes:
                    best = cand
                    break
            if best is None:
                best = scored[0]
            print(f"    最佳匹配: {best['code']} {best['name']} 评分={best['score']} 差异={best['diff_pct']}%")
            if best["score"] >= 60:
                conf = "high"
            elif best["score"] >= 40:
                conf = "medium"
            else:
                conf = "low"

            new_identified.append({
                "code": best["code"],
                "name": best["name"],
                "current_price": best["current_price"],
                "confidence": conf,
                "score": int(best["score"]),
                "minute_price_match": best["diff_pct"],
            })
            already_codes.add(best["code"])
            if best["score"] >= 40:
                print(f"    [OK] 保存识别: {best['code']} {best['name']} ({conf})")
        else:
            print(f"    无匹配")

    return new_identified


def save_to_db(portfolio_info: Dict, positions: List, identified: List[Dict] = None):
    """将识别结果保存到SQLite数据库"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.storage.portfolio_db import PortfolioDB
        db = PortfolioDB(DB_PATH)
        db.save_snapshot(portfolio_info, positions or [], identified)
        return True
    except Exception as e:
        print(f"  [WARN] DB save failed: {e}")
        return False

# ===================== 监控循环 =====================

def load_state() -> Dict:
    """加载保存的状态"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
    return {"last_buy_records": {}, "last_positions": {}}

def save_state(state: Dict):
    """保存状态"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def save_results(results: List[Dict]):
    """保存识别结果"""
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def detect_new_buy(portfolio_id: int, state: Dict) -> Tuple[bool, Optional[Dict]]:
    """检测是否有新的买入"""
    prev_records = state.get("last_buy_records", {})
    prev_positions = state.get("last_positions", {})

    info = fetch_portfolio_info(portfolio_id)
    positions = fetch_position_list(portfolio_id)

    if not info or not positions:
        return False, None

    current_record = info.get("portfolioStockRecord")
    if not current_record:
        return False, None

    # 创建当前记录签名
    current_signature = f"{current_record.get('zqdm')}|{current_record.get('cjbh')}|{current_record.get('mdate')}"
    prev_signature = prev_records.get(str(portfolio_id), "")

    is_new = current_signature != prev_signature

    # 更新状态
    prev_records[str(portfolio_id)] = current_signature
    state["last_buy_records"] = prev_records

    if is_new and prev_signature:
        print(f"\n  [NEW] 检测到新买入! {current_record.get('zqmc','****')} {current_record.get('mdate')}")
        return True, current_record
    elif is_new and not prev_signature:
        print(f"\n  [首次] 初始买入记录: {current_record.get('mdate')}")
        return False, current_record

    return False, None

def monitor_loop():
    """主监控循环"""
    print("=" * 60)
    print("  组合持仓监控系统 v1.0")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"\n监控组合:")
    for pid, pinfo in PORTFOLIOS.items():
        print(f"  #{pid}: {pinfo['name']} - {pinfo['advisor']}")
    print(f"\n模式: 无新买入→5-10min随机 | 检测到新买入→1min高频")
    print("-" * 60)

    state = load_state()
    high_freq_mode = False
    high_freq_cycles = 0
    max_high_freq_cycles = 30  # 最多高频30次(30分钟)后恢复普通模式
    last_identify_results = {}

    # 首次运行识别当前持仓
    print(f"\n[首次启动] 识别当前持仓...")
    for pid in PORTFOLIOS:
        try:
            result = identify_stock_by_buy(pid)
            if result:
                last_identify_results[str(pid)] = result
                save_results(list(last_identify_results.values()))
        except Exception as e:
            print(f"  [ERROR] identify #{pid} failed: {e}")

    cycle_count = 0
    while True:
        cycle_count += 1
        now = datetime.now()
        print(f"\n[{now.strftime('%H:%M:%S')}] 第{cycle_count}轮检查 {'[HIGH]高频' if high_freq_mode else '🔄常规'}")

        for pid in PORTFOLIOS:
            is_new, record = detect_new_buy(pid, state)

            if is_new:
                print(f"\n  [HIGH] 组合 #{pid} 检测到新买入!")
                high_freq_mode = True
                high_freq_cycles = 0

                # 尝试识别股票
                try:
                    result = identify_stock_by_buy(pid)
                    if result:
                        last_identify_results[str(pid)] = result
                        save_results(list(last_identify_results.values()))
                        identified = result.get("identified_stocks", [])
                        if identified:
                            print(f"\n  [OK] 识别成功: {identified[0]['code']} {identified[0]['name']}")
                except Exception as e:
                    print(f"  [ERROR] identify #{pid} failed: {e}")
            elif record:
                # 有记录但非新，持续尝试识别 (高频模式下每分钟都查)
                if high_freq_mode:
                    try:
                        result = identify_stock_by_buy(pid)
                        if result:
                            last_identify_results[str(pid)] = result
                            save_results(list(last_identify_results.values()))
                            identified = result.get("identified_stocks", [])
                            if identified:
                                print(f"\n  [OK] 识别成功: {identified[0]['code']} {identified[0]['name']}")
                                high_freq_mode = False  # 识别成功退出高频
                    except Exception as e:
                        print(f"  [ERROR] identify #{pid} failed: {e}")

        # 保存状态
        save_state(state)

        # 决定下一次间隔
        if high_freq_mode:
            high_freq_cycles += 1
            if high_freq_cycles >= max_high_freq_cycles:
                print(f"\n  [INFO] 高频模式已达到{max_high_freq_cycles}次上限，切换回常规模式")
                high_freq_mode = False
            interval = 60  # 1分钟
        else:
            interval = random.randint(300, 600)  # 5-10分钟

        next_check = datetime.now() + timedelta(seconds=interval)
        print(f"\n  下次检查: {timedelta(seconds=interval)} 后 ({next_check})")
        time.sleep(interval)


# ===================== 主入口 =====================

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--identify":
        # 仅识别模式
        if "--portfolio" in sys.argv:
            idx = sys.argv.index("--portfolio")
            pids = [int(sys.argv[idx + 1])]
        else:
            pids = list(PORTFOLIOS.keys())

        all_results = []
        result_map = {}
        for pid in pids:
            result = identify_stock_by_buy(pid)
            if result:
                all_results.append(result)
                result_map[pid] = result
            else:
                # 最新调仓识别失败也不丢组合：继续做持仓识别+入库
                print(f"\n[WARN] 组合 #{pid} 最新调仓识别失败，继续保存持仓/调仓/走势")
                result_map[pid] = {
                    "portfolio_id": pid,
                    "identified_stocks": [],
                    "buy_record": None,
                }

        if all_results:
            save_results(all_results)
            print(f"\n结果已保存至: {RESULTS_FILE}")

        # 无论最新调仓是否识别成功，都保存每个组合的完整快照
        from src.storage.portfolio_db import PortfolioDB as PDB2
        pdb = PDB2(DB_PATH)
        for pid in pids:
            r = result_map.get(pid) or {
                "portfolio_id": pid,
                "identified_stocks": [],
                "buy_record": None,
            }
            info = analyze_positions(pid)
            if "error" in info:
                print(f"  [ERROR] analyze #{pid}: {info['error']}")
                continue
            positions = fetch_position_list(pid)
            identified = list(r.get("identified_stocks", []))
            for item in identified:
                if r.get("buy_record"):
                    item["buy_price"] = r["buy_record"].get("buy_price", 0)

            print(f"\n[存量持仓识别] 组合 #{pid}...")
            extra = identify_existing_positions(pid, positions or [], identified)
            if extra:
                existing_codes = set(i.get("code", "") for i in identified)
                for e in extra:
                    if e["code"] not in existing_codes:
                        identified.append(e)
                        existing_codes.add(e["code"])
                        if r.get("buy_record"):
                            e["buy_price"] = r["buy_record"].get("buy_price", 0)
                        print(f"  [ADD] {e['code']} {e['name']} (score={e['score']})")
                    else:
                        print(f"  [SKIP] {e['code']} {e['name']} - already identified")

            deal_records = fetch_deal_records(pid)
            chart_data = fetch_profit_chart(pid)
            if deal_records:
                print(f"  [Trades] 获取到 {len(deal_records)} 条调仓记录")
            if chart_data:
                print(f"  [Chart] 获取到收益走势数据 ({chart_data.get('date','').count(';')+1} 个交易日)")

            pdb.save_snapshot(info, positions or [], identified,
                              trades=deal_records, chart_data=chart_data)
            print(f"  [OK] 组合 #{pid} 已保存 (持仓{len(positions or [])} 识别{len(identified)})")

    elif len(sys.argv) > 1 and sys.argv[1] == "--summary":
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.storage.portfolio_db import PortfolioDB
        db = PortfolioDB(DB_PATH)
        print("\n=== 数据库摘要 ===")
        print(db.summary())

    elif len(sys.argv) > 2 and sys.argv[1] == "--export":
        pid = int(sys.argv[2])
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.storage.portfolio_db import PortfolioDB
        import json
        db = PortfolioDB(DB_PATH)
        data = db.export_json(pid)
        out = CACHE_DIR / f"portfolio_{pid}_export.json"
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已导出 {pid} 数据到 {out}")

    else:
        # 监控模式
        monitor_loop()

if __name__ == "__main__":
    main()
