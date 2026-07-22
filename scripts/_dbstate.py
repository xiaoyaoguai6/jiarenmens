import sqlite3, datetime
c = sqlite3.connect(r"D:\project\jiarenmens\data\crawl_data.db")
c.row_factory = sqlite3.Row
print("today:", datetime.date.today().isoformat())
print()
print("zh_id       | pos_max       | trd_max        | plr_updated_at")
for r in c.execute("""
SELECT p.zh_id,
       (SELECT MAX(crawl_date) FROM positions WHERE zh_id=p.zh_id) AS pos_max,
       (SELECT MAX(crawl_date) FROM trades    WHERE zh_id=p.zh_id) AS trd_max,
       p.updated_at AS upd
FROM players p
WHERE p.zh_id IN (SELECT zh_id FROM positions UNION SELECT zh_id FROM trades)
ORDER BY p.updated_at DESC
"""):
    print(f'  {r["zh_id"]:<11} | {str(r["pos_max"]):<13} | {str(r["trd_max"]):<13} | {r["upd"]}')