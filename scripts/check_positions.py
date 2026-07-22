# -*- coding: utf-8 -*-
import sqlite3
conn = sqlite3.connect('data/crawl_data.db')

# 查看所有表
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor]
print("Tables:", tables)

# 检查 positions 表是否有数据
if 'positions' in tables:
    cursor = conn.execute('SELECT COUNT(*) FROM positions')
    count = cursor.fetchone()[0]
    print(f"\nPositions count: {count}")
    if count > 0:
        print("\nTop 20 stocks by holdings:")
        cursor = conn.execute('''
            SELECT stock_code, stock_name, COUNT(*) as holder_count 
            FROM positions 
            GROUP BY stock_code 
            ORDER BY holder_count DESC 
            LIMIT 20
        ''')
        for row in cursor:
            print(f"  {row[1]} ({row[0]}): {row[2]} holders")
else:
    print("\nNo positions table found")

conn.close()
