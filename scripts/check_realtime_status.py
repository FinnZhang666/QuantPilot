#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import get_session_factory
from app.realtime.manager import STATUS_TEXT
from app.realtime.repository import RealtimeRepository

PID_PATH = Path(__file__).resolve().parents[1] / "data" / "realtime.pid"


def main() -> int:
    db = get_session_factory()()
    try:
        row = RealtimeRepository(db).status()
        running = False
        if PID_PATH.exists():
            try:
                os.kill(int(PID_PATH.read_text(encoding="utf-8")), 0)
                running = True
            except Exception:
                running = False
        metadata = row.metadata_json or {}
        print("实时行情服务状态")
        print("进程：" + ("运行中" if running else "未运行"))
        print("运行状态：" + STATUS_TEXT.get(row.status, "未知"))
        print("订阅标的：" + str(len(row.subscribed_symbols_json or [])))
        print("订阅类型：" + "、".join(row.subscribed_types_json or []))
        print("最近行情：" + str(row.last_message_at or "暂无"))
        print("累计接收：%s" % metadata.get("received", 0))
        print("累计写入：%s" % metadata.get("persisted", 0))
        print("累计丢弃：%s" % metadata.get("dropped", 0))
        print("重连次数：%s" % row.reconnect_count)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

