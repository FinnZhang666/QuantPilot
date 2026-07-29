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
from app.database.models import CandidatePoolEntry, CandidatePoolRun, MarketRegime
from app.candidate_pool.service import CandidatePoolService
from app.market_regime.service import MarketRegimeService
from app.review.service import OpportunityReviewService
from sqlalchemy import select

PID_FILE = Path("data/opportunity_runtime.pid")


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="QuantPilot管理CLI")
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
    regime = group.add_parser("regime")
    regime_actions = regime.add_subparsers(dest="action", required=True)
    regime_actions.add_parser("evaluate")
    regime_actions.add_parser("current")
    regime_history = regime_actions.add_parser("history")
    regime_history.add_argument("--limit", type=int, default=20)
    regime_history.add_argument("--json", action="store_true")
    candidates = group.add_parser("candidates")
    candidate_actions = candidates.add_subparsers(dest="action", required=True)
    for action in ("build", "refresh", "runs"):
        item = candidate_actions.add_parser(action)
        item.add_argument("--json", action="store_true")
    candidate_list = candidate_actions.add_parser("list")
    candidate_list.add_argument("--date")
    candidate_list.add_argument("--direction")
    candidate_list.add_argument("--min-score", type=int, default=0)
    candidate_list.add_argument("--limit", type=int, default=20)
    candidate_list.add_argument("--json", action="store_true")
    candidate_show = candidate_actions.add_parser("show")
    candidate_show.add_argument("--symbol", required=True)
    candidate_show.add_argument("--json", action="store_true")
    candidate_expire = candidate_actions.add_parser("expire")
    candidate_expire.add_argument("--id", type=int, required=True)
    review = group.add_parser("review")
    review_actions = review.add_subparsers(dest="action", required=True)
    review_run = review_actions.add_parser("run")
    review_run.add_argument("--limit", type=int, default=100)
    review_run.add_argument("--symbol")
    review_pending = review_actions.add_parser("pending")
    review_pending.add_argument("--limit", type=int, default=100)
    review_pending.add_argument("--symbol")
    review_show = review_actions.add_parser("show")
    review_show.add_argument("--id", type=int, required=True)
    return parser


def main():
    args = build_parser().parse_args()
    if args.group == "regime":
        return _regime(args)
    if args.group == "candidates":
        return _candidates(args)
    if args.group == "review":
        return _review(args)
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
        "【QuantPilot】Telegram测试消息。"
    ))
    print("Telegram测试结果：%s" % result.status)
    return 0 if result.status == "sent" else 1


def _regime(args):
    with get_session_factory()() as db:
        settings = get_settings()
        service = MarketRegimeService(db, settings)
        if args.action == "evaluate":
            row = service.evaluate(force=True)
            print("市场状态评估完成：%s，可信度 %s，LONG/SHORT偏好 %s/%s" % (
                row.regime, row.confidence, row.long_bias, row.short_bias,
            ))
            return 0
        if args.action == "current":
            rows = [service.current()]
        else:
            rows = list(db.scalars(select(MarketRegime).order_by(
                MarketRegime.bar_time.desc(),
            ).limit(args.limit)))
        rows = [row for row in rows if row]
        if getattr(args, "json", False):
            print(json.dumps([_regime_dict(row) for row in rows], ensure_ascii=False, default=str))
        elif not rows:
            print("暂无Market Regime记录。")
        else:
            for row in rows:
                print("%s %s 可信度%s LONG/SHORT %s/%s" % (
                    row.bar_time, row.regime, row.confidence, row.long_bias, row.short_bias,
                ))
    return 0


def _review(args):
    with get_session_factory()() as db:
        service = OpportunityReviewService(db, get_settings())
        if args.action == "run":
            result = service.run(limit=args.limit, symbol=args.symbol)
            print("Opportunity复盘完成：扫描 %(scanned)s，完成 %(reviewed)s，待复盘 %(pending)s，失败 %(failed)s。" % result)
            return 0 if result["failed"] == 0 else 1
        if args.action == "pending":
            rows = service.pending(limit=args.limit, symbol=args.symbol)
            print("待复盘数量：%s" % len(rows))
            for row in rows:
                print("#%s %s %s %s %s" % (
                    row.id, row.symbol, row.timeframe, row.direction, row.status,
                ))
            return 0
        row = service.get(args.id)
        if row is None:
            print("Opportunity Review不存在。")
            return 2
        print("Review #%s：%s，窗口 %s" % (row.id, row.review_status, row.review_window))
        print("收益：%s%%，MFE：%s%%，MAE：%s%%" % (
            row.return_percent, row.mfe_percent, row.mae_percent,
        ))
        print("持有：%s根K线 / %s分钟" % (row.holding_bars, row.holding_minutes))
        print("原因：%s" % json.dumps(row.reason_json, ensure_ascii=False))
    return 0


def _candidates(args):
    with get_session_factory()() as db:
        service = CandidatePoolService(db, get_settings())
        if args.action == "build":
            row = service.build("MANUAL")
            return _print_candidate_run(row, args.json)
        if args.action == "refresh":
            row = service.refresh()
            return _print_candidate_run(row, args.json)
        if args.action == "expire":
            row = service.expire(args.id)
            print("候选 #%s 已过期：%s" % (row.id, row.symbol))
            return 0
        if args.action == "runs":
            rows = list(db.scalars(select(CandidatePoolRun).order_by(
                CandidatePoolRun.started_at.desc(),
            ).limit(20)))
            if args.json:
                print(json.dumps([_run_dict(row) for row in rows], ensure_ascii=False, default=str))
            else:
                for row in rows:
                    print("#%s %s %s 候选%s 错误%s" % (
                        row.id, row.run_type, row.status, row.candidate_count, row.error_count,
                    ))
            return 0
        query = select(CandidatePoolEntry)
        if args.action == "show":
            query = query.where(CandidatePoolEntry.symbol == args.symbol.upper().replace("US.", ""))
        else:
            query = query.where(CandidatePoolEntry.final_score >= args.min_score)
            if args.date:
                query = query.where(CandidatePoolEntry.pool_date == args.date)
            if args.direction:
                query = query.where(CandidatePoolEntry.direction == args.direction.upper())
        rows = list(db.scalars(query.order_by(
            CandidatePoolEntry.pool_date.desc(), CandidatePoolEntry.rank,
        ).limit(getattr(args, "limit", 20))))
        if args.json:
            print(json.dumps([_candidate_dict(row) for row in rows], ensure_ascii=False, default=str))
        elif not rows:
            print("暂无符合条件的候选。")
        else:
            for row in rows:
                print("#%s %s %s LONG/SHORT %s/%s 最终%s %s" % (
                    row.rank, row.symbol, row.direction, row.long_score,
                    row.short_score, row.final_score, row.status,
                ))
    return 0


def _print_candidate_run(row, as_json):
    value = _run_dict(row)
    if as_json:
        print(json.dumps(value, ensure_ascii=False, default=str))
    else:
        print("候选池构建：%s，Universe %s，扫描 %s，候选 %s（LONG %s / SHORT %s / BOTH %s）" % (
            row.status, row.universe_size, row.scanned_size, row.candidate_count,
            row.long_count, row.short_count, row.both_count,
        ))
    return 0 if row.status in {"COMPLETED", "DEGRADED"} else 1


def _regime_dict(row):
    return {"id": row.id, "regime": row.regime, "confidence": row.confidence,
            "long_bias": row.long_bias, "short_bias": row.short_bias, "bar_time": row.bar_time}


def _candidate_dict(row):
    return {"id": row.id, "symbol": row.symbol, "direction": row.direction,
            "long_score": row.long_score, "short_score": row.short_score,
            "final_score": row.final_score, "rank": row.rank, "status": row.status,
            "pool_date": row.pool_date, "reasons": row.reason_snapshot_json}


def _run_dict(row):
    return {"id": row.id, "run_type": row.run_type, "status": row.status,
            "universe_size": row.universe_size, "scanned_size": row.scanned_size,
            "candidate_count": row.candidate_count, "long_count": row.long_count,
            "short_count": row.short_count, "both_count": row.both_count,
            "error_count": row.error_count}


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
