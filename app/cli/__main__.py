import argparse
import asyncio
import json
import os
import signal
import time
from pathlib import Path

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.notifications.telegram import TelegramNotificationProvider
from app.runtime.realtime_runtime import get_runtime
from app.services.opportunity_service import OpportunityService
from app.database.models import RuntimeStatus
from sqlalchemy import select

PID_FILE = Path("data/opportunity_runtime.pid")


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Moomoo Quant管理CLI")
    group = parser.add_subparsers(dest="group", required=True)
    runtime = group.add_parser("runtime")
    runtime_actions = runtime.add_subparsers(dest="action", required=True)
    runtime_actions.add_parser("start")
    runtime_actions.add_parser("stop")
    runtime_actions.add_parser("status")
    opportunities = group.add_parser("opportunities")
    op_actions = opportunities.add_subparsers(dest="action", required=True)
    list_parser = op_actions.add_parser("list")
    list_parser.add_argument("--limit", type=int, default=10)
    show = op_actions.add_parser("show")
    show.add_argument("--symbol", required=True)
    telegram = group.add_parser("telegram")
    telegram.add_subparsers(dest="action", required=True).add_parser("test")
    return parser


def main():
    args = build_parser().parse_args()
    if args.group == "runtime":
        if args.action == "start":
            return _runtime_foreground()
        if args.action == "stop":
            return _runtime_stop()
        with get_session_factory()() as db:
            row = db.scalar(select(RuntimeStatus).where(RuntimeStatus.service_name == "realtime_runtime"))
            opend = db.scalar(select(RuntimeStatus).where(RuntimeStatus.service_name == "opend"))
        result = {
            "status": row.status if row else "STOPPED",
            "status_text": "已停止" if row is None or row.status == "STOPPED" else row.status,
            "opend_connected": bool(opend and opend.status == "CONNECTED"),
        }
        print("Runtime状态：%s（%s）" % (result["status_text"], result["status"]))
        print("OpenD连接：%s" % ("正常" if result["opend_connected"] else "未连接"))
        return 0
    if args.group == "opportunities":
        with get_session_factory()() as db:
            rows = OpportunityService(db).recent(
                limit=getattr(args, "limit", 10),
                symbol=getattr(args, "symbol", None),
            )
            if not rows:
                print("暂无Opportunity。")
            for row in rows:
                print("%s %s %s %s分 %s" % (
                    row.symbol, row.timeframe, row.direction, row.score, row.status,
                ))
        return 0
    settings = get_settings()
    if not settings.telegram_enabled:
        print("Telegram未启用，请先配置TELEGRAM_BOT_TOKEN和TELEGRAM_CHAT_IDS。")
        return 2
    result = asyncio.run(TelegramNotificationProvider(settings).send_text(
        "【Moomoo Quant】Sprint 07 Telegram测试消息。"
    ))
    print("Telegram测试结果：%s" % result.status)
    return 0 if result.status == "sent" else 1


def _runtime_foreground():
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        try:
            old = json.loads(PID_FILE.read_text(encoding="utf-8"))
            os.kill(int(old["pid"]), 0)
            print("Runtime已经运行，PID：%s" % old["pid"])
            return 0
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            PID_FILE.unlink()
    runtime = get_runtime()
    result = runtime.start()
    PID_FILE.write_text(json.dumps({
        "pid": os.getpid(), "project": str(Path.cwd().resolve()),
        "service": "moomoo-opportunity-runtime",
    }), encoding="utf-8")
    stopping = {"value": False}

    def stop_handler(signum, frame):
        stopping["value"] = True

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    print("Runtime状态：%s（PID %s）" % (result["status_text"], os.getpid()))
    try:
        while not stopping["value"]:
            time.sleep(1)
    finally:
        runtime.stop()
        if PID_FILE.exists():
            PID_FILE.unlink()
    print("Runtime已安全停止。")
    return 0


def _runtime_stop():
    if not PID_FILE.exists():
        print("Runtime未运行或PID文件不存在。")
        return 0
    try:
        payload = json.loads(PID_FILE.read_text(encoding="utf-8"))
        pid = int(payload["pid"])
        if payload.get("service") != "moomoo-opportunity-runtime":
            raise ValueError("PID文件服务标识不匹配")
        os.kill(pid, signal.SIGTERM)
        print("已请求Runtime安全停止，PID：%s" % pid)
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("Runtime PID无效：%s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
