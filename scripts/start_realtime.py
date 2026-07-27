#!/usr/bin/env python3
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.realtime.factory import build_realtime_manager
from app.realtime.manager import STATUS_TEXT

PID_PATH = Path(__file__).resolve().parents[1] / "data" / "realtime.pid"


def main() -> int:
    parser = argparse.ArgumentParser(description="启动Moomoo实时行情服务（只读）")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--duration", type=int, default=0, help="运行秒数；0表示持续运行")
    args = parser.parse_args()
    if args.duration < 0:
        parser.error("运行时间不能为负数")
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            print("实时行情服务可能已运行，PID：%s" % pid)
            return 1
        except (ValueError, ProcessLookupError, PermissionError):
            PID_PATH.unlink(missing_ok=True)
    manager = build_realtime_manager(get_settings(), args.symbols)
    stopping = False

    def stop_handler(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    try:
        result = manager.start()
        print("实时行情服务状态：" + STATUS_TEXT[manager.status.value])
        print("订阅成功：" + json.dumps(result.successful, ensure_ascii=False))
        if result.failed:
            print("订阅失败：" + json.dumps(result.failed, ensure_ascii=False))
        started = time.monotonic()
        while not stopping and (args.duration == 0 or time.monotonic() - started < args.duration):
            time.sleep(0.2)
        manager.stop()
        report = manager.get_status()
        print("实时行情服务已安全停止")
        print("收到：%s，写入：%s，重复：%s，丢弃：%s，错误：%s，队列峰值：%s，停止后队列：%s" % (
            report.received_count, report.persisted_count, report.duplicate_count,
            report.dropped_count, report.error_count, manager.max_queue_size, report.queue_size,
        ))
        print("分类接收：" + json.dumps(manager.received_by_type, ensure_ascii=False))
        if manager.error_samples:
            print("错误样本：" + json.dumps(manager.error_samples, ensure_ascii=False))
        return 0
    except Exception as exc:
        print("实时行情服务启动失败：%s：%s" % (type(exc).__name__, exc))
        try:
            manager.stop()
        except Exception:
            pass
        return 1
    finally:
        if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_PATH.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
