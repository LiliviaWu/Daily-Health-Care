"""
列出提醒数据库状态，便于检查是否已标记完成。
用法:
    python reminder_db_dump.py            # 列出全部
    python reminder_db_dump.py completed  # 只看已完成
"""

import sys
from reminder_module import ReminderManager


def main():
    status = sys.argv[1] if len(sys.argv) > 1 else None
    mgr = ReminderManager(enable_mqtt=False)
    reminders = mgr.list_reminders(status=status)

    if not reminders:
        print("无记录")
        return

    for r in reminders:
        print(
            f"id={r.id} status={r.status} severity={r.severity} due={r.due_time} "
            f"user={r.user_id} tags={r.tags} content={r.content}"
        )


if __name__ == "__main__":
    main()
