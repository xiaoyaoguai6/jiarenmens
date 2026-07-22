import sqlite3, json
db = "D:\\project\\jiarenmens\\data\\crawl_data.db"
c = sqlite3.connect(db); c.row_factory = sqlite3.Row

print("=== table counts ===")
for t in ("players","positions","trades"):
    n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n}")

print()
print("=== positions by zh ===")
for row in c.execute("SELECT zh_id, COUNT(*) n, ROUND(SUM(position_ratio),2) pos_sum FROM positions GROUP BY zh_id"):
    print(f"  zh={row['zh_id']} n={row['n']} sum_pos={row['pos_sum']}%")

print()
print("=== trades by zh / direction ===")
for row in c.execute("SELECT zh_id, direction, COUNT(*) n, GROUP_CONCAT(DISTINCT trade_date) dates FROM trades GROUP BY zh_id, direction ORDER BY zh_id, direction"):
    print(f"  zh={row['zh_id']} dir={row['direction']:5s} n={row['n']} dates={row['dates']}")

print()
print("=== alerts.log tail ===")
from pathlib import Path
p = Path("D:\\project\\jiarenmens\\data\\alerts.log")
lines = p.read_text(encoding="utf-8").splitlines()
print(f"  total {len(lines)} alerts; first 3 / last 3:")
for ln in lines[:3]:
    print(f"   {ln}")
print("   ...")
for ln in lines[-3:]:
    print(f"   {ln}")