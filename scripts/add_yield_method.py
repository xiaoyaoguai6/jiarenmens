# -*- coding: utf-8 -*-
"""Add fetch_yield_history method to PlayerListSpider."""
import re

with open("src/spiders/player_list.py", "r", encoding="utf-8") as f:
    code = f.read()

# Add fetch_yield_history method before fetch_player_list
method_code = '''
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

'''

# Insert before fetch_player_list
code = code.replace(
    "    def fetch_player_list(",
    method_code + "    def fetch_player_list(",
    1
)

with open("src/spiders/player_list.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Added fetch_yield_history method")
