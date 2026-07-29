from datetime import datetime, timezone
import asyncio
import threading
from typing import Optional, Tuple

import httpx

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import CandidateSignal, Opportunity, RealtimeServiceStatus, RuntimeStatus
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
            return True, "可用命令：/status、/opportunities、/symbol TICKER、/why TICKER、/help"
        if name == "/status":
            return True, self._status()
        if name == "/opportunities":
            return True, self._opportunities()
        if name in {"/symbol", "/why"}:
            if len(parts) != 2:
                return False, "请提供Ticker，例如：%s SOXL" % name
            symbol = parts[1].upper().replace("US.", "")
            return True, self._symbol(symbol) if name == "/symbol" else self._why(symbol)
        return False, "未知命令。发送 /help 查看可用命令。"

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
