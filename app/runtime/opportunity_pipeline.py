import asyncio
from datetime import timezone
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import CandidateSignal, Opportunity
from app.notifications.telegram import TelegramNotificationProvider
from app.services.opportunity_service import OpportunityService
from app.strategy.service import StrategyRunner
from app.runtime.runtime_state import RuntimeStateRepository


class OpportunityPipeline:
    def __init__(
        self, db: Session, settings: Settings,
        notifier: Optional[TelegramNotificationProvider] = None,
        strategy_runner: Optional[StrategyRunner] = None,
    ):
        self.db = db
        self.settings = settings
        self.service = OpportunityService(
            db, settings.opportunity_min_score,
            settings.opportunity_default_expiry_bars,
        )
        self.notifier = notifier or TelegramNotificationProvider(settings, db)
        self.strategy_runner = strategy_runner or StrategyRunner(db, settings)

    def process_closed_bar(self, symbol: str, timeframe: str) -> Dict[str, object]:
        symbol = symbol.upper().replace("US.", "")
        state = RuntimeStateRepository(self.db)
        state.update("opportunity_pipeline", "RUNNING", {"symbol": symbol, "timeframe": timeframe})
        try:
            result = self.strategy_runner.run(
                [symbol], [timeframe], mode="REALTIME",
                auto_calculate_features=True,
            )
            signal = self.db.scalar(select(CandidateSignal).where(
                CandidateSignal.symbol == symbol,
                CandidateSignal.timeframe == timeframe,
            ).order_by(desc(CandidateSignal.bar_timestamp), desc(CandidateSignal.id)).limit(1))
            if signal is None:
                return {"symbol": symbol, "status": "NO_SIGNAL"}
            opportunity, created = self.service.from_signal(signal)
            if opportunity is not None and created:
                self._notify_new(opportunity)
            for invalidated in self.service.last_invalidated:
                self._notify_invalidated(invalidated)
            state.update(
                "opportunity_pipeline", "RUNNING",
                {"symbol": symbol, "timeframe": timeframe, "signal_type": signal.signal_type},
                success=True,
            )
            return {
                "symbol": symbol, "status": "SUCCESS",
                "signal_type": signal.signal_type,
                "opportunity_id": opportunity.id if opportunity else None,
                "created": created, "strategy_run": result,
            }
        except Exception as exc:
            self.db.rollback()
            state.update("opportunity_pipeline", "DEGRADED", error=type(exc).__name__ + "：" + str(exc))
            return {"symbol": symbol, "status": "ERROR", "error": type(exc).__name__ + "：" + str(exc)}

    def _notify_new(self, opportunity: Opportunity) -> None:
        message = self.format_opportunity(opportunity)
        try:
            result = asyncio.run(self.notifier.send_text(message))
        except Exception as exc:
            self.service.mark_notification_failed(opportunity.id, type(exc).__name__)
            RuntimeStateRepository(self.db).update("telegram", "DEGRADED", error=type(exc).__name__)
            return
        if result.status == "sent":
            message_id = result.message_ids[0] if result.message_ids else None
            self.service.update_status(opportunity.id, "NOTIFIED", message_id)
            RuntimeStateRepository(self.db).update("telegram", "CONNECTED", success=True)
        elif result.status == "disabled":
            opportunity.notification_status = "DISABLED"
            self.db.commit()
            RuntimeStateRepository(self.db).update("telegram", "DISABLED")
        else:
            self.service.mark_notification_failed(opportunity.id, result.error or result.status)
            RuntimeStateRepository(self.db).update("telegram", "DEGRADED", error=result.error or result.status)

    def _notify_invalidated(self, opportunity: Opportunity) -> None:
        message = (
            "【交易机会失效】\n\n股票：%s\n周期：%s\n方向：%s\n"
            "原Opportunity #%s 已不再满足策略条件，状态更新为INVALIDATED。\n"
            "该消息仅用于研究状态跟踪，不是交易指令。"
        ) % (opportunity.symbol, opportunity.timeframe, opportunity.direction, opportunity.id)
        try:
            result = asyncio.run(self.notifier.send_text(message))
            if result.status == "failed":
                self.service.mark_notification_failed(opportunity.id, result.error or "发送失败")
                RuntimeStateRepository(self.db).update("telegram", "DEGRADED", error=result.error or "发送失败")
        except Exception as exc:
            self.service.mark_notification_failed(opportunity.id, type(exc).__name__)
            RuntimeStateRepository(self.db).update("telegram", "DEGRADED", error=type(exc).__name__)

    @staticmethod
    def format_opportunity(row: Opportunity) -> str:
        strategy = row.strategy_snapshot_json or {}
        reasons = "\n".join("- " + value for value in strategy.get("reasons", [])) or "- 暂无"
        risks = "\n".join("- " + value for value in strategy.get("risks", [])) or "- 默认参数尚未回测优化"
        source = row.bar_time if row.bar_time.tzinfo else row.bar_time.replace(tzinfo=timezone.utc)
        beijing = source.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
        eastern = source.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
        return (
            "【新交易机会】\n\n股票：%s\n方向：%s\n周期：%s\n策略：%s\n"
            "评分：%s\n参考价格：%s\n状态：等待确认\n\n核心原因：\n%s\n\n"
            "风险：\n%s\n\n时间：北京时间 %s / 美东时间 %s\n\n"
            "仅代表交易机会，建议关注并等待确认，不构成收益承诺或即时交易指令。"
        ) % (
            row.symbol, "做多" if row.direction == "LONG" else "做空",
            row.timeframe, row.strategy_name, row.score,
            row.entry_reference_price, reasons, risks, beijing, eastern,
        )
