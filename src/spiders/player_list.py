"""
Player list spider using the rt_get_rank API.

The rt_get_rank endpoint is the ONLY working API. All individual detail
APIs (rt_get_info, rt_get_position, etc.) return -10000 server-side rejection,
and the info/detail HTML pages have had their data-loading JS gutted.
So we enrich player profiles using rank data from all 5 time periods.
"""
import requests
from typing import List, Dict, Any
from src.config import BASE_URL, USER_AGENT
from src.utils.logger import setup_logger

logger = setup_logger()

RANK_TYPES = {
    "10004": ("总榜", "return_total"),
    "10003": ("年榜", "return_250d"),
    "10001": ("月榜", "return_20d"),
    "10000": ("周榜", "return_5d"),
    "10005": ("日榜", "return_daily"),
}


class PlayerListSpider:
    """Fetch the top N players from each rank type, deduplicate, and enrich."""

    API_URL = "https://emdcspzhapi.dfcfs.cn/rtV1"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": BASE_URL,
        })

    def fetch_rank_players(self, rank_type: str, max_count: int = 500) -> list:
        """Fetch players for a single rank type (paginated)."""
        players = []
        offset = 0
        page_size = 20

        while offset < max_count:
            request_size = min(page_size, max_count - offset)

            params = {
                "type": "rt_get_rank",
                "rankType": rank_type,
                "recIdx": offset,
                "recCnt": request_size,
                "rankid": 0,
                "appVer": "9001000",
            }

            try:
                response = self.session.get(self.API_URL, params=params, timeout=30)
                data = response.json()

                if data.get("result") != "0" or not data.get("data"):
                    break

                batch = data.get("data", [])
                if not batch:
                    break

                for p in batch:
                    players.append({
                        "zh_id": p.get("zjzh", ""),
                        "name": p.get("zhuheName", ""),
                        "user_id": p.get("userid", ""),
                        "followers": int(p.get("concernCnt", 0)),
                        "labels": [l for l in [p.get("label1", ""), p.get("label2", ""), p.get("label3", "")] if l],
                        "rateForApp": float(p.get("rateForApp", 0)),
                        "rateTitle": p.get("rateTitle", ""),
                    })

                if len(batch) < request_size:
                    break

                offset += len(batch)

            except Exception as e:
                logger.error(f"Failed to fetch rank {rank_type}: {e}")
                break

        return players[:max_count]

    def fetch_all_ranks(self, max_per_rank: int = 500) -> dict:
        """Fetch all rank types."""
        all_ranks = {}

        for rank_type, (rank_name, _field) in RANK_TYPES.items():
            logger.info(f"Fetching {rank_name} (top {max_per_rank})...")
            players = self.fetch_rank_players(rank_type, max_per_rank)
            all_ranks[rank_type] = players
            logger.info(f"  {rank_name}: {len(players)} players")

        return all_ranks


    def fetch_yield_history(self, zh_id, yk_type="1", index_code="000300"):
        """Fetch yield history via rt_zhuhe_yk_new. yk_type: 1=daily, 5=weekly."""
        params = {
            "type": "rt_zhuhe_yk_new", "zh": zh_id,
            "recIdx": "0", "recCnt": "365",
            "ykType": yk_type, "indexCode": index_code,
            "appVer": "9001000",
        }
        try:
            r = self.session.get(self.API_URL, params=params, timeout=15)
            d = r.json()
            if d.get("result") == "0" and isinstance(d.get("data"), list):
                return d["data"]
        except Exception as e:
            logger.debug("Yield history failed for %s: %s" % (zh_id, e))
        return []

    def fetch_player_list(self, max_per_rank: int = 500) -> list:
        """
        Fetch all rank types, merge / deduplicate, and enrich each player
        with return rates from every rank they appear in.
        """
        logger.info(f"Fetching player list (top {max_per_rank} per rank)")

        all_ranks = self.fetch_all_ranks(max_per_rank)

        player_map = {}

        for rank_type, (_rank_name, field_key) in RANK_TYPES.items():
            for p in all_ranks.get(rank_type, []):
                zh_id = p.get("zh_id")
                if not zh_id:
                    continue

                if zh_id not in player_map:
                    player_map[zh_id] = {
                        "zh_id": zh_id,
                        "name": p.get("name", ""),
                        "user_id": p.get("user_id", ""),
                        "followers": p.get("followers", 0),
                        "labels": p.get("labels", []),
                        "ranks": [],
                        "return_total": None,
                        "return_250d": None,
                        "return_20d": None,
                        "return_5d": None,
                        "return_daily": None,
                    }

                entry = player_map[zh_id]
                rank_label = RANK_TYPES[rank_type][0]
                if rank_label not in entry["ranks"]:
                    entry["ranks"].append(rank_label)
                entry[field_key] = p.get("rateForApp", 0)
                if p.get("followers", 0) > entry["followers"]:
                    entry["followers"] = p["followers"]
                p_labels = p.get("labels", [])
                if len(p_labels) > len(entry["labels"]):
                    entry["labels"] = p_labels

        logger.info(f"After dedup: {len(player_map)} unique players")
        return list(player_map.values())


def crawl_player_list(max_per_rank: int = 500) -> list:
    """Convenience wrapper."""
    spider = PlayerListSpider()
    return spider.fetch_player_list(max_per_rank)


if __name__ == "__main__":
    players = crawl_player_list(max_per_rank=500)
    print(f"\nTotal: {len(players)} players")
    if players:
        print("Sample:")
        for k, v in players[0].items():
            print(f"  {k}: {v}")
