""""
告警推送脚本
============
读取 monitor_alerts 表中未发送的告警，输出到 stdout。
配合 Hermes cron 定时任务，输出内容会自动推送到用户的微信。

用法:
    python scripts/push_alerts.py
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "crawl_data.db"
ALERTS_FILE = ROOT / "data" / "alerts.json"


def main():
    # 检查是否有未发送的告警
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, zh_id, message, created_at FROM monitor_alerts WHERE sent=0 ORDER BY created_at ASC"
        ).fetchall()

    if not rows:
        # 没有新告警，静默退出
        return

    # 构建输出消息
    output = []
    ids = []
    for row in rows:
        alert_id, zh_id, message, created_at = row
        output.append(f"📢 选手调仓提醒 [{created_at}]")
        output.append(message)
        output.append("─" * 40)
        ids.append(alert_id)

    # 输出到 stdout（Hermes cron 会捕获并推送到微信）
    print("\n".join(output))

    # 标记为已发送
    with sqlite3.connect(DB_PATH) as conn:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE monitor_alerts SET sent=1 WHERE id IN ({placeholders})", ids
        )

    # 同时更新 alerts.json 标记已发送
    if ALERTS_FILE.exists():
        try:
            alerts = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
            now = datetime.now().isoformat()
            for a in alerts:
                a["pushed"] = now
            ALERTS_FILE.write_text(
                json.dumps(alerts, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()