from datetime import datetime, timezone
import asyncio
import threading
from typing import Optional, Tuple

import httpx

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import (
    CandidatePoolEntry, CandidateSignal, MarketRegime, Opportunity,
    RealtimeServiceStatus, RuntimeStatus,
    OpportunityReview,
    AIReviewAnalysis,
)
from app.database.session import get_session_factory
from app.notifications.telegram import TelegramNotificationProvider
from app.runtime.runtime_state import RuntimeStateRepository


class TelegramCommandService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def handle(self, user_id: str, command: str) -> Tuple[bool, str]:
        if str(user_id) not in self.settings.telegram_admin_id_set():
            return False, "权限不足：该命令仅允许Telegram管理员使用。"
        parts = command.strip().split()
        name = parts[0].lower() if parts else ""
        if name == "/help":
            return True, (
                "可用命令：/status、/opportunities、/symbol TICKER、/why TICKER、"
                "/regime、/candidates、/long、/short、/candidate TICKER、/help"
                "、/review [TICKER|pending]"
                "、/ai_review [TICKER|pending|failed|ID]"
            )
        if name == "/status":
            return True, self._status()
        if name == "/opportunities":
            return True, self._opportunities()
        if name in {"/symbol", "/why"}:
            if len(parts) != 2:
                return False, "请提供Ticker，例如：%s SOXL" % name
            symbol = parts[1].upper().replace("US.", "")
            return True, self._symbol(symbol) if name == "/symbol" else self._why(symbol)
        if name == "/regime":
            return True, self._regime()
        if name in {"/candidates", "/long", "/short"}:
            direction = name[1:].upper() if name in {"/long", "/short"} else None
            return True, self._candidates(direction)
        if name == "/candidate":
            if len(parts) != 2:
                return False, "请提供Ticker，例如：/candidate SOXL"
            return True, self._candidate(parts[1].upper().replace("US.", ""))
        if name == "/review":
            argument = parts[1] if len(parts) > 1 else None
            return True, self._review(argument)
        if name == "/ai_review":
            argument = parts[1] if len(parts) > 1 else None
            return True, self._ai_review(argument)
        return False, "未知命令。发送 /help 查看可用命令。"

    def _ai_review(self, argument=None) -> str:
        if argument and argument.lower() == "pending":
            count = self.db.scalar(select(func.count()).select_from(AIReviewAnalysis).where(
                AIReviewAnalysis.provider != "mock",
                AIReviewAnalysis.status.in_(["PENDING", "RUNNING"]),
            )) or 0
            return "AI Review待处理：%s" % count
        query = select(AIReviewAnalysis, OpportunityReview, Opportunity).join(
            OpportunityReview, OpportunityReview.id == AIReviewAnalysis.opportunity_review_id,
        ).join(
            Opportunity, Opportunity.id == AIReviewAnalysis.opportunity_id,
        ).where(AIReviewAnalysis.provider != "mock")
        if argument and argument.lower() == "failed":
            query = query.where(AIReviewAnalysis.status == "FAILED")
        elif argument and argument.isdigit():
            query = query.where(AIReviewAnalysis.id == int(argument))
        elif argument:
            query = query.where(Opportunity.symbol == argument.upper().replace("US.", ""))
        else:
            query = query.where(AIReviewAnalysis.status == "COMPLETED")
        rows = list(self.db.execute(query.order_by(
            desc(AIReviewAnalysis.created_at),
        ).limit(5)))
        if not rows:
            return "暂无已完成的 AI Review 分析。"
        lines = ["【AI Review Analyst】"]
        for analysis, review, opportunity in rows:
            historical = analysis.historical_comparison_json or {}
            items = analysis.investigation_items_json or []
            top = "；".join(item.get("title", "") for item in items[:2]) or "无"
            lines.append(
                "%s %s %s/%s\n收益%s%% MFE%s%% MAE%s%%\n分类：%s，可信度：%s\n"
                "摘要：%s\n调查：%s" % (
                    opportunity.symbol, opportunity.direction,
                    opportunity.strategy_name, opportunity.timeframe,
                    review.return_percent, review.mfe_percent, review.mae_percent,
                    historical.get("outcome_classification", "UNKNOWN"),
                    analysis.confidence_score if analysis.confidence_score is not None else "—",
                    analysis.summary or "暂无", top,
                )
            )
        lines.append("\nAI分析仅供研究与复盘，不构成投资建议。")
        return "\n\n".join(lines)

    def _review(self, argument=None) -> str:
        if argument and argument.lower() == "pending":
            count = self.db.scalar(select(func.count()).select_from(Opportunity).where(
                Opportunity.status.in_(["ACTIVE", "EXPIRED", "REVIEW_PENDING"]),
            )) or 0
            return "待复盘Opportunity：%s\nReview结果不构成交易建议。" % count
        query = select(OpportunityReview, Opportunity).join(
            Opportunity, Opportunity.id == OpportunityReview.opportunity_id,
        )
        if argument:
            query = query.where(Opportunity.symbol == argument.upper().replace("US.", ""))
        rows = self.db.execute(query.order_by(
            desc(OpportunityReview.review_time),
        ).limit(10)).all()
        if not rows:
            return "暂无%sReview记录。" % ((argument.upper() + " ") if argument else "")
        completed = [
            review for review, _ in rows
            if review.review_status == "REVIEWED" and review.return_percent is not None
        ]
        average_return = sum(float(row.return_percent) for row in completed) / len(completed) if completed else 0
        average_mfe = sum(float(row.mfe_percent) for row in completed) / len(completed) if completed else 0
        average_mae = sum(float(row.mae_percent) for row in completed) / len(completed) if completed else 0
        lines = [
            "【最近Opportunity Review】",
            "完成：%s\n平均收益：%.2f%%\n平均MFE：%.2f%%\n平均MAE：%.2f%%" % (
                len(completed), average_return, average_mfe, average_mae,
            ),
            "",
        ]
        lines.extend("%s %s %s 收益%s%% MFE%s%% MAE%s%%" % (
            opportunity.symbol, opportunity.timeframe, review.review_status,
            review.return_percent if review.return_percent is not None else "—",
            review.mfe_percent if review.mfe_percent is not None else "—",
            review.mae_percent if review.mae_percent is not None else "—",
        ) for review, opportunity in rows)
        lines.append("\nReview结果不构成交易建议。")
        return "\n".join(lines)

    def _status(self) -> str:
        runtime = self.db.scalar(select(RuntimeStatus).where(RuntimeStatus.service_name == "realtime_runtime"))
        opend = self.db.scalar(select(RealtimeServiceStatus).where(
            RealtimeServiceStatus.service_name == "moomoo_realtime",
        ))
        today = datetime.now(timezone.utc).date()
        count = self.db.scalar(select(func.count()).select_from(Opportunity).where(
            Opportunity.detected_at >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        )) or 0
        metadata = runtime.metadata_json if runtime else {}
        return (
            "Runtime状态：%s\nOpenD状态：%s\n最后行情：%s\n"
            "最后策略运行：%s\n今日Opportunity：%s"
        ) % (
            runtime.status if runtime else "STOPPED",
            opend.status if opend else "UNKNOWN",
            opend.last_message_at if opend else None,
            metadata.get("last_strategy_run_at"), count,
        )

    def _opportunities(self) -> str:
        rows = self.db.scalars(select(Opportunity).order_by(
            desc(Opportunity.detected_at),
        ).limit(10)).all()
        if not rows:
            return "暂无Opportunity。"
        return "\n".join(
            "%s %s %s %s分 %s" % (
                row.symbol, row.timeframe, row.direction, row.score, row.status,
            ) for row in rows
        )

    def _symbol(self, symbol: str) -> str:
        row = self.db.scalar(select(Opportunity).where(
            Opportunity.symbol == symbol,
        ).order_by(desc(Opportunity.detected_at)).limit(1))
        signal = self.db.scalar(select(CandidateSignal).where(
            CandidateSignal.symbol == symbol,
        ).order_by(desc(CandidateSignal.bar_timestamp)).limit(1))
        return "Ticker：%s\n最近Opportunity：%s\n最新策略状态：%s" % (
            symbol,
            ("%s/%s/%s分" % (row.timeframe, row.status, row.score)) if row else "无",
            signal.signal_type if signal else "无Signal",
        )

    def _why(self, symbol: str) -> str:
        signal = self.db.scalar(select(CandidateSignal).where(
            CandidateSignal.symbol == symbol,
        ).order_by(desc(CandidateSignal.bar_timestamp), desc(CandidateSignal.id)).limit(1))
        if signal is None:
            return "%s暂无策略判断。" % symbol
        passed = signal.reasons_json or []
        failed = signal.risks_json or []
        return (
            "%s最近策略判断：%s\n评分：%s，可信度：%s\n\n通过条件：\n%s\n\n"
            "未通过或风险：\n%s\n\n原因：%s"
        ) % (
            symbol, signal.signal_type, signal.score, signal.confidence,
            "\n".join("- " + value for value in passed) or "- 无",
            "\n".join("- " + value for value in failed) or "- 无",
            signal.summary_zh,
        )

    def _regime(self) -> str:
        row = self.db.scalar(select(MarketRegime).order_by(
            desc(MarketRegime.bar_time),
        ).limit(1))
        if row is None:
            return "当前市场状态：UNKNOWN（尚无有效评估）。"
        snapshot = row.reason_snapshot_json or {}
        reasons = "\n".join("- " + value for value in snapshot.get("reasons", [])[:5]) or "- 无"
        risks = "\n".join("- " + value for value in snapshot.get("risks", [])[:5]) or "- 无"
        return (
            "【市场状态】\n状态：%s\n可信度：%s\nLONG/SHORT偏好：%s/%s\n"
            "主要原因：\n%s\n主要风险：\n%s\n\nMarket Regime不是独立买卖信号。"
        ) % (row.regime, row.confidence, row.long_bias, row.short_bias, reasons, risks)

    def _candidates(self, direction=None) -> str:
        query = select(CandidatePoolEntry).where(
            CandidatePoolEntry.status.in_(["CANDIDATE", "RESEARCHING", "QUALIFIED"]),
        )
        if direction:
            query = query.where(CandidatePoolEntry.direction.in_([direction, "BOTH"]))
        rows = self.db.scalars(query.order_by(
            desc(CandidatePoolEntry.pool_date), CandidatePoolEntry.rank,
        ).limit(10)).all()
        if not rows:
            return "暂无符合条件的候选。"
        title = "LONG候选" if direction == "LONG" else ("SHORT候选" if direction == "SHORT" else "当前候选池")
        lines = ["【%s】" % title]
        lines.extend("%s. %s %s %s分" % (
            row.rank or index, row.symbol, row.direction, row.final_score,
        ) for index, row in enumerate(rows, 1))
        lines.append("\n候选仅代表进入进一步研究范围，不构成交易指令。")
        return "\n".join(lines)

    def _candidate(self, symbol: str) -> str:
        row = self.db.scalar(select(CandidatePoolEntry).where(
            CandidatePoolEntry.symbol == symbol,
        ).order_by(desc(CandidatePoolEntry.pool_date), CandidatePoolEntry.rank).limit(1))
        if row is None:
            return "%s当前不在候选池中。" % symbol
        snapshot = row.reason_snapshot_json or {}
        reasons = "\n".join("- " + value for value in snapshot.get("reasons", [])[:6]) or "- 无"
        risks = "\n".join("- " + value for value in snapshot.get("risks", [])[:6]) or "- 无"
        return (
            "%s候选详情\n方向：%s\nLONG/SHORT：%s/%s\n最终评分：%s\n"
            "原因：\n%s\n风险：\n%s\n\n不构成交易指令。"
        ) % (symbol, row.direction, row.long_score, row.short_score, row.final_score, reasons, risks)


class TelegramCommandPoller:
    """Restricted getUpdates poller. It exposes read-only commands and no trading actions."""

    def __init__(self, settings: Settings, session_factory=None):
        self.settings = settings
        self.session_factory = session_factory or get_session_factory()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.offset = 0

    def start(self) -> bool:
        if not self.settings.telegram_enabled:
            return False
        if self.thread and self.thread.is_alive():
            return True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name="telegram-command-poller", daemon=False)
        self.thread.start()
        return True

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=8)

    def _loop(self) -> None:
        url = "https://api.telegram.org/bot%s/getUpdates" % self.settings.telegram_bot_token
        while not self.stop_event.is_set():
            try:
                response = httpx.get(
                    url, params={"offset": self.offset, "timeout": 5, "allowed_updates": '["message"]'},
                    timeout=8,
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    self.offset = max(self.offset, int(update["update_id"]) + 1)
                    self._handle_update(update)
                self._state("CONNECTED", success=True)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self._state("DEGRADED", error=type(exc).__name__)
                self.stop_event.wait(2)

    def _handle_update(self, update) -> None:
        message = update.get("message") or {}
        text = message.get("text") or ""
        user_id = str((message.get("from") or {}).get("id", ""))
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if not text.startswith("/") or not chat_id:
            return
        db = self.session_factory()
        try:
            _, answer = TelegramCommandService(db, self.settings).handle(user_id, text)
            asyncio.run(TelegramNotificationProvider(self.settings, db).send_text(answer, [chat_id]))
        finally:
            db.close()

    def _state(self, status: str, error: Optional[str] = None, success: bool = False) -> None:
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update("telegram", status, error=error, success=success)
        finally:
            db.close()
