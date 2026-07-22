"""Smart mitmproxy addon for East Money shipan player scraping.

When the Android EM App (com.eastmoney.android.berlin) views a player's
position/trade page, it issues rtV3 requests whose bodies contain
method + combinationId (zh_id).  This addon:

1. Detects hosts that match the EM rtV3 endpoint (spzhapi.dfcfs.cn).
2. Parses responses for two methods of interest and emits structured
   JSON events to data/recon/positions.jsonl:
     - CombinationHoldPositionPermitHandler  -> snapshot of full holdings
     - CombinationRelocatePositionHandler    -> snapshot of recent trades

Each event has: ts, kind, zh_id, method, raw_body_preview, parsed.
The downstream poller consumes this file (append-only) and updates SQLite.

Usage:
  mitmdump -s scripts/mitm_em_position_extractor.py -p 0.0.0.0:8080
"""
import json
import re
import time
from pathlib import Path

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"
RECON_DIR.mkdir(parents=True, exist_ok=True)

POSITIONS_LOG = RECON_DIR / "positions.jsonl"

TARGET_METHODS = {
    # berlin APP rtV3 method names
    "CombinationHoldPositionPermitHandler": "position",
    "CombinationRelocatePositionHandler": "trade",
    "CombinationHoldBlockPermitHandler": "block",  # sector breakdown (optional)
}

# 证券 APP endpoints may use older style.  Until we know their method names,
# also dump every request/response for target hosts so we can see them live.
ALL_DUMP_LOG = RECON_DIR / "raw_dump.jsonl"


def is_target(host: str) -> bool:
    if not host:
        return False
    h = host.lower()
    # berlin APP target: spzhapi.dfcfs.cn   (rtV3)
    # 证券 APP target: emdcspzhapi.eastmoney.com / spzhapi.eastmoney.com  (rtV2 / rtV1)
    return (h.endswith("dfcfs.cn")
            or "spzhapi" in h
            or "emdcspzhapi" in h)


def parse_request_body(body: str) -> dict:
    """Extract method + combinationId from request body JSON."""
    try:
        j = json.loads(body)
    except Exception:
        return {}
    m = j.get("method", "")
    args = j.get("args", {})
    zid = args.get("combinationId") or args.get("zh") or ""
    if isinstance(zid, str):
        zid = zid.strip().strip('"')
    return {"method": m, "zh_id": str(zid), "request_id": j.get("randomCode", "")}


def extract_positions(resp_json: dict, zh_id: str) -> list:
    """
    Response for CombinationHoldPositionPermitHandler is a list of sector buckets
    where each bucket has `data` array of stock rows.

    Sample (from our capture):
    [
      {"blkRatio":"88","BlockName":"通信设备","data":[
        {"market":"1","stkMktCode":"SH600105","__code":"600105","__name":"永鼎股份",
         "cbj":"43.184","__zxjg":"49.040","webYkRate":"13.56","holdPos":"88",
         "positionRateDetail":"87.954023","showDigit":"0","fullcode":"402669889"}
      ],"blkPositionRateDetail":"87.954023","blkShowDigit":"0"},
      {"blkRatio":"12","BlockName":"现金","data":[]}
    ]

    Maps to rows: zh_id, stock_code, stock_name, sector, cost_price, current_price,
                  profit_ratio, position_ratio, raw fields preserved.
    """
    positions = []
    data = resp_json.get("data")
    # If server returns the sector-list schema
    if isinstance(data, list) and data and isinstance(data[0], dict) and "BlockName" in data[0]:
        for bucket in data:
            sector = bucket.get("BlockName", "")
            blk_ratio = bucket.get("blkRatio", "")
            for row in bucket.get("data", []) or []:
                positions.append({
                    "zh_id": zh_id,
                    "stock_code": row.get("__code") or row.get("stkCode") or "",
                    "stock_name": row.get("__name") or row.get("stkName") or "",
                    "sector": sector,
                    "sector_ratio": blk_ratio,
                    "market": row.get("market", ""),
                    "stk_mkt_code": row.get("stkMktCode", ""),
                    "cost_price": float(row.get("cbj", 0) or 0),
                    "current_price": float(row.get("__zxjg") or row.get("__zxjg")
                                            or row.get("zxjg") or 0),
                    "profit_ratio": float(row.get("webYkRate") or 0),
                    "position_ratio": float(row.get("holdPos") or
                                             row.get("positionRateDetail") or 0),
                    "raw": row,
                })
    elif isinstance(data, dict) and "pages" in data:
        # alternate schema: trades listed in pages
        for page_row in data.get("pages", []):
            positions.append({
                "zh_id": zh_id,
                "stock_code": page_row.get("stkCode", ""),
                "stock_name": page_row.get("stkName", ""),
                "sector": "",
                "raw": page_row,
            })
    return positions


def extract_trades(resp_json: dict, zh_id: str) -> dict:
    """
    Response for CombinationRelocatePositionHandler is one of two shapes:
    Schema A: {"data":{"openCombination":false}}  -> the combination is closed/no public
    Schema B: {"data":{"pages":[{"stkCode":"600105","bsMark":"S","relocateQty":3700,...}],
               "totalCount":1,"pageIndex":1,"totalPages":1}}

    Schema C: {"data":{"totalYieldRate":"8.5030","dayYieldRate":"0.0000",...}}  -> yields only
    """
    data = resp_json.get("data", {})
    if isinstance(data, dict) and "pages" in data:
        trades = []
        for row in data.get("pages", []) or []:
            trades.append({
                "zh_id": zh_id,
                "stock_code": row.get("stkCode", ""),
                "stock_name": row.get("stkName", ""),
                "market": row.get("market", ""),
                "trade_date": row.get("bizDate", ""),
                "relocate_time": row.get("relocateTime", ""),
                "direction": "buy" if row.get("bsMark") == "B" else "sell",
                "qty": int(row.get("relocateQty", 0) or 0),
                "price": float(row.get("relocatePrice", 0) or 0),
                "position_ratio": row.get("positionRatio", ""),
                "raw": row,
            })
        return {
            "kind": "trade_list",
            "total_pages": data.get("totalPages"),
            "page_index": data.get("pageIndex"),
            "total_count": data.get("totalCount"),
            "trades": trades,
        }
    elif isinstance(data, dict) and "openCombination" in data:
        return {"kind": "closed", "openCombination": data.get("openCombination")}
    elif isinstance(data, dict) and "totalYieldRate" in data:
        return {"kind": "yields", "fields": data}
    return {"kind": "unknown", "data": data}


def emit_event(ev: dict):
    line = json.dumps(ev, ensure_ascii=False, default=str)
    with POSITIONS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    # also print for live tail
    print(line, flush=True)


from mitmproxy import http


class PositionExtractorAddon:
    """Pairs an rtV3 request with its response and emits structured events."""

    def __init__(self):
        # in-flight request attrs keyed by (mitm flow id)
        self._req_attrs = {}

    def request(self, flow: http.HTTPFlow):
        host = flow.request.host or ""
        if not is_target(host):
            return
        try:
            body_text = flow.request.get_text(strict=False) or ""
        except Exception:
            body_text = ""
        # Raw dump for debugging unknown schemas / methods
        try:
            with ALL_DUMP_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": time.time(),
                    "phase": "request",
                    "url": flow.request.url,
                    "host": host,
                    "method_http": flow.request.method,
                    "headers": dict(flow.request.headers),
                    "body": body_text[:2000],
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        parsed = parse_request_body(body_text)
        # Also accept url?method=X style rtV1 GET requests
        if not parsed.get("method") and flow.request.method == "GET":
            from urllib.parse import urlparse
            qs = urlparse(flow.request.url).query
            from urllib.parse import parse_qs
            q = parse_qs(qs)
            method = q.get("type", q.get("method", [""]))[0]
            zid = q.get("zh", q.get("zhid", [""]))[0]
            parsed = {"method": method, "zh_id": zid, "request_id": ""}
        if not parsed.get("method"):
            return
        self._req_attrs[id(flow)] = parsed

    def response(self, flow: http.HTTPFlow):
        host = flow.request.host or ""
        if not is_target(host):
            return
        parsed = self._req_attrs.pop(id(flow), None)
        # Always raw dump the response, even if method not recognized
        try:
            with ALL_DUMP_LOG.open("a", encoding="utf-8") as f:
                body_text = flow.response.get_text(strict=False) if flow.response else ""
                f.write(json.dumps({
                    "ts": time.time(),
                    "phase": "response",
                    "url": flow.request.url,
                    "host": host,
                    "status": flow.response.status_code if flow.response else None,
                    "len": len(flow.response.content) if flow.response and flow.response.content else 0,
                    "headers": dict(flow.response.headers) if flow.response else {},
                    "body": (body_text or "")[:3000],
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        if not parsed:
            return
        method = parsed["method"]
        zh_id = parsed["zh_id"]
        if method not in TARGET_METHODS:
            return
        try:
            text = flow.response.get_text(strict=False)
            resp_json = json.loads(text)
        except Exception as e:
            emit_event({
                "ts": time.time(),
                "kind": "parse_error",
                "zh_id": zh_id,
                "method": method,
                "error": str(e),
                "raw_text": (text or "")[:1000],
            })
            return
        kind_label = TARGET_METHODS[method]
        if kind_label == "position":
            payload = extract_positions(resp_json, zh_id)
        elif kind_label == "trade":
            payload = extract_trades(resp_json, zh_id)
        else:
            payload = resp_json.get("data", {})
        emit_event({
            "ts": time.time(),
            "kind": kind_label,
            "zh_id": zh_id,
            "method": method,
            "code": resp_json.get("code"),
            "message": resp_json.get("message"),
            "data": payload,
        })


addons = [PositionExtractorAddon()]