import html
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import (
    CompanionAnalysis,
    InvestmentPortfolio,
    MarketRegime,
    PortfolioHolding,
    PortfolioWatchlist,
    SystemPaperAccount,
    SystemPaperPosition,
    TelegramAdminRecord,
    TelegramAIInvocation,
    TelegramFeedbackRecord,
    TelegramRuntimeMessageLog,
    TelegramRuntimeUser,
    TradeReview,
)
from app.telegram_product.bot_profiles import TelegramBotProfile
from app.telegram_runtime.ai import TelegramAIService
from app.telegram_runtime.renderer import (
    TelegramMessage,
    about_message,
    ai_message,
    callback_keyboard,
    feedback_categories,
    help_message,
    language_picker,
    main_menu,
    more,
    updates_message,
    welcome,
)
from app.telegram_runtime.transport import TelegramBotTransport
from app.portfolio_center.errors import DuplicateSymbol, ValidationError
from app.portfolio_center.service import PortfolioService, WatchlistService


FEEDBACK_CATEGORIES = {"BUG", "FEATURE", "STRATEGY", "HELPFUL", "NOT_HELPFUL"}


class TelegramProductService:
    def __init__(
        self, db: Session, settings: Settings, transport: TelegramBotTransport,
        ai_service: Optional[TelegramAIService] = None,
    ):
        self.db = db
        self.settings = settings
        self.transport = transport
        self.ai = ai_service or TelegramAIService(db, settings)

    def handle_update(
        self, profile: TelegramBotProfile, update: Dict[str, object],
    ) -> Tuple[Optional[str], Optional[TelegramMessage]]:
        callback = update.get("callback_query") or {}
        message = callback.get("message") if callback else update.get("message") or {}
        chat = message.get("chat") or {}
        actor = callback.get("from") if callback else message.get("from") or {}
        chat_id = str(chat.get("id") or "")
        if not chat_id or not actor.get("id"):
            return None, None
        user = self._upsert_user(actor, chat_id, profile)
        if callback:
            callback_id = str(callback.get("id") or "")
            if callback_id:
                self.transport.answer_callback(profile.token, callback_id)
            action = str(callback.get("data") or "").removeprefix("tc:")
            response = self._action(profile, user, action, None)
        else:
            text = str(message.get("text") or "").strip()
            response = self._incoming_text(profile, user, text)
        return chat_id, response

    def _upsert_user(
        self, actor: Dict[str, object], chat_id: str, profile: TelegramBotProfile,
    ) -> TelegramRuntimeUser:
        telegram_user_id = str(actor["id"])
        user = self.db.scalar(select(TelegramRuntimeUser).where(
            TelegramRuntimeUser.telegram_user_id == telegram_user_id,
        ))
        if user is None:
            user = TelegramRuntimeUser(
                telegram_user_id=telegram_user_id, chat_id=chat_id,
                language=self.settings.ai_companion_default_language,
                last_bot_alias=profile.alias,
                pending_context_json={"language_selected": False},
            )
            self.db.add(user)
        user.chat_id = chat_id
        user.username = actor.get("username")
        user.first_name = actor.get("first_name")
        user.last_name = actor.get("last_name")
        user.last_bot_alias = profile.alias
        user.last_seen_at = datetime.now(timezone.utc)
        username = str(actor.get("username") or "").lower()
        if username:
            admin = self.db.scalar(select(TelegramAdminRecord).where(
                func.lower(TelegramAdminRecord.username) == username,
                TelegramAdminRecord.enabled.is_(True),
            ))
            if admin and not admin.telegram_user_id:
                admin.telegram_user_id = telegram_user_id
                admin.bound_at = datetime.now(timezone.utc)
        self.db.commit()
        return user

    def _incoming_text(
        self, profile: TelegramBotProfile, user: TelegramRuntimeUser, text: str,
    ) -> TelegramMessage:
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            command = parts[0].split("@", 1)[0].lstrip("/").lower()
            argument = parts[1].strip() if len(parts) > 1 else None
            return self._action(profile, user, command, argument)
        if not self._language_selected(user):
            return language_picker()
        if user.pending_action == "ANALYZE":
            user.pending_action = None
            self.db.commit()
            return self._stock_analysis_message(profile, user, text)
        if user.pending_action == "WATCHLIST_ADD":
            user.pending_action = None
            self.db.commit()
            return self._add_watchlist_symbol(user, text)
        if user.pending_action and user.pending_action.startswith("FEEDBACK:"):
            category = user.pending_action.split(":", 1)[1]
            user.pending_action = None
            feedback = TelegramFeedbackRecord(
                user_id=user.id, bot_alias=profile.alias, language=user.language,
                category=category, message=text[:4000],
            )
            self.db.add(feedback)
            self.db.commit()
            self._notify_admins(profile, feedback, user)
            return TelegramMessage(
                "反馈已提交，谢谢。" if user.language == "zh-CN" else "Feedback submitted. Thank you.",
                main_menu(user.language),
            )
        context = dict(user.pending_context_json or {})
        if context.get("ai_followup_active"):
            return self._ai_followup_message(profile, user, text, context)
        symbols = self._parse_symbols(text)
        if symbols:
            return self._stock_analysis_message(profile, user, text)
        return welcome(profile, user.language)

    def _action(
        self, profile: TelegramBotProfile, user: TelegramRuntimeUser,
        action: str, argument: Optional[str],
    ) -> TelegramMessage:
        action = action.lower()
        if action == "start":
            self._clear_ai_followup(user)
            return welcome(profile, user.language) if self._language_selected(user) else language_picker()
        if not self._language_selected(user) and not action.startswith("language:"):
            return language_picker()
        self._clear_ai_followup(user)
        if action in {"analyze", "ai_analysis"}:
            if argument:
                return self._stock_analysis_message(profile, user, argument)
            user.pending_action = "ANALYZE"
            self.db.commit()
            return TelegramMessage(
                "请输入股票代码，例如 PLTR；批量可输入 PLTR, MULL, SOXL（最多 5 个）。"
                if user.language == "zh-CN" else
                "Enter a symbol such as PLTR, or up to 5 symbols: PLTR, MULL, SOXL.",
            )
        if action in {"portfolio", "investments"}:
            return self._portfolio(user)
        if action == "market":
            return self._market(user)
        if action == "more":
            return more(user.language)
        if action == "help":
            return help_message(user.language)
        if action == "updates":
            return updates_message(user.language)
        if action == "about":
            return about_message(user.language)
        if action == "watchlist":
            return self._watchlist(user)
        if action == "watchlist:add":
            user.pending_action = "WATCHLIST_ADD"
            self.db.commit()
            return TelegramMessage(
                "请输入股票代码，例如 PLTR。" if user.language == "zh-CN" else
                "Enter a stock symbol, for example PLTR.",
                callback_keyboard([[
                    ("取消" if user.language == "zh-CN" else "Cancel", "watchlist"),
                ]]),
            )
        if action == "holding":
            return self._holdings(user)
        if action == "history":
            return self._history(user)
        if action == "review":
            return self._reviews(user)
        if action == "feedback":
            return feedback_categories(user.language)
        if action.startswith("feedback:"):
            category = action.split(":", 1)[1].upper()
            if category not in FEEDBACK_CATEGORIES:
                return feedback_categories(user.language)
            if category in {"HELPFUL", "NOT_HELPFUL"}:
                feedback = TelegramFeedbackRecord(
                    user_id=user.id, bot_alias=profile.alias, language=user.language,
                    category=category, message=category,
                )
                self.db.add(feedback)
                self.db.commit()
                self._notify_admins(profile, feedback, user)
                return TelegramMessage(
                    "已记录，谢谢。" if user.language == "zh-CN" else "Recorded. Thank you.",
                    main_menu(user.language),
                )
            user.pending_action = "FEEDBACK:" + category
            self.db.commit()
            return TelegramMessage(
                "请发送反馈内容。" if user.language == "zh-CN" else "Send the feedback details.",
            )
        if action == "language":
            return language_picker()
        if action.startswith("language:"):
            language = {"zh-cn": "zh-CN", "en-us": "en-US"}.get(action.split(":", 1)[1])
            if language:
                user.language = language
                context = dict(user.pending_context_json or {})
                context["language_selected"] = True
                user.pending_context_json = context
                self.db.commit()
            return welcome(profile, user.language)
        if action.startswith("position_explain:"):
            return self._ai_message(profile, user, "POSITION_EXPLAIN", action.split(":", 1)[1])
        if action.startswith("trade_explain:"):
            return self._ai_message(profile, user, "TRADE_EXPLAIN", action.split(":", 1)[1])
        if action == "strategy_review":
            return self._ai_message(profile, user, "STRATEGY_REVIEW", None)
        if action == "market_summary":
            return self._ai_message(profile, user, "MARKET_SUMMARY", None)
        return more(user.language)

    @staticmethod
    def _language_selected(user: TelegramRuntimeUser) -> bool:
        return bool((user.pending_context_json or {}).get("language_selected"))

    def _ai_message(
        self, profile: TelegramBotProfile, user: TelegramRuntimeUser,
        operation: str, symbol: Optional[str],
    ) -> TelegramMessage:
        result = self.ai.explain(operation, user.language, profile.alias, user.id, symbol)
        invocation = self.db.scalar(select(TelegramAIInvocation).where(
            TelegramAIInvocation.user_id == user.id,
        ).order_by(desc(TelegramAIInvocation.id)).limit(1))
        if invocation and invocation.status == "FALLBACK" and self.settings.ai_companion_enabled:
            self._notify_admin_event(profile, "AI_ERROR", "AI Companion used fallback.")
        return ai_message(result, user.language)

    @staticmethod
    def _parse_symbols(value: str) -> List[str]:
        parts = re.split(r"[\s,，;；]+", str(value or "").upper().strip())
        result = []
        for raw in parts:
            symbol = raw.removeprefix("US.").strip()
            if not symbol or not (1 <= len(symbol) <= 12):
                continue
            if not symbol.replace(".", "").replace("-", "").isalnum():
                continue
            if symbol not in result:
                result.append(symbol)
        return result[:5]

    def _stock_analysis_message(
        self, profile: TelegramBotProfile, user: TelegramRuntimeUser, value: str,
    ) -> TelegramMessage:
        symbols = self._parse_symbols(value)
        if not symbols:
            return TelegramMessage(
                "未识别到有效股票代码，请重新输入。" if user.language == "zh-CN" else
                "No valid stock symbol was found. Please try again.",
            )
        if len(symbols) == 1:
            result = self._ai_message(profile, user, "STOCK_ANALYSIS", symbols[0])
            self._remember_ai_context(user, symbols)
            return result
        sections = []
        for symbol in symbols:
            result = self.ai.explain(
                "STOCK_ANALYSIS", user.language, profile.alias, user.id, symbol,
            )
            sections.append("## %s\n%s" % (symbol, result))
        self._remember_ai_context(user, symbols)
        return ai_message("\n\n".join(sections), user.language)

    def _ai_followup_message(
        self, profile: TelegramBotProfile, user: TelegramRuntimeUser,
        question: str, context: Dict[str, object],
    ) -> TelegramMessage:
        symbols = [str(value) for value in context.get("last_analysis_symbols") or []][:5]
        safe_question = self._safe_followup_question(question)
        if not safe_question:
            return TelegramMessage(
                "请输入与最近分析相关的问题。" if user.language == "zh-CN" else
                "Enter a question about the latest analysis.",
            )
        result = self.ai.explain(
            "STOCK_FOLLOW_UP", user.language, profile.alias, user.id,
            symbols[0] if symbols else None,
            question=safe_question, related_symbols=symbols,
        )
        return ai_message(result, user.language)

    def _remember_ai_context(
        self, user: TelegramRuntimeUser, symbols: List[str],
    ) -> None:
        context = dict(user.pending_context_json or {})
        context["ai_followup_active"] = True
        context["last_analysis_symbols"] = list(symbols[:5])
        user.pending_context_json = context
        self.db.commit()

    def _clear_ai_followup(self, user: TelegramRuntimeUser) -> None:
        context = dict(user.pending_context_json or {})
        context.pop("ai_followup_active", None)
        context.pop("last_analysis_symbols", None)
        user.pending_context_json = context
        self.db.commit()

    @staticmethod
    def _safe_followup_question(value: str) -> str:
        text = str(value or "").strip()[:1000]
        text = re.sub(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b", "[REDACTED]", text)
        text = re.sub(r"\b(?:AIza|AQ\.)[A-Za-z0-9_.-]{20,}\b", "[REDACTED]", text)
        text = re.sub(
            r"(?i)\b(password|cookie|api[_ -]?key|token)\s*[:=]\s*\S+",
            r"\1=[REDACTED]", text,
        )
        return text

    def _portfolio(self, user: TelegramRuntimeUser) -> TelegramMessage:
        portfolio_ids = list(self.db.scalars(select(InvestmentPortfolio.id).where(
            InvestmentPortfolio.user_id == user.telegram_user_id,
        )))
        holdings = list(self.db.scalars(select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id.in_(portfolio_ids), PortfolioHolding.status == "OPEN",
        ))) if portfolio_ids else []
        if user.language == "zh-CN":
            text = "💼 我的投资\n\n投资组合：%d\n当前持仓：%d" % (len(portfolio_ids), len(holdings))
        else:
            text = "💼 My Investments\n\nPortfolios: %d\nOpen holdings: %d" % (len(portfolio_ids), len(holdings))
        return TelegramMessage(text)

    def _market(self, user: TelegramRuntimeUser) -> TelegramMessage:
        row = self.db.scalar(select(MarketRegime).order_by(
            desc(MarketRegime.bar_time), desc(MarketRegime.id),
        ).limit(1))
        if row is None:
            return TelegramMessage("暂无市场快照。" if user.language == "zh-CN" else "No market snapshot yet.")
        if user.language == "zh-CN":
            text = "🌍 市场快照\n\n状态：%s\n趋势：%s\n动量：%s\n风险：%s\n置信度：%s" % (
                row.regime, row.trend_score, row.momentum_score, row.risk_score, row.confidence,
            )
        else:
            text = "🌍 Market Snapshot\n\nRegime: %s\nTrend: %s\nMomentum: %s\nRisk: %s\nConfidence: %s" % (
                row.regime, row.trend_score, row.momentum_score, row.risk_score, row.confidence,
            )
        return TelegramMessage(text)

    def _watchlist(self, user: TelegramRuntimeUser) -> TelegramMessage:
        portfolio_ids = list(self.db.scalars(select(InvestmentPortfolio.id).where(
            InvestmentPortfolio.user_id == user.telegram_user_id,
        )))
        rows = list(self.db.scalars(select(PortfolioWatchlist).where(
            PortfolioWatchlist.portfolio_id.in_(portfolio_ids),
        ).order_by(PortfolioWatchlist.display_order).limit(20))) if portfolio_ids else []
        symbols = ", ".join(row.symbol for row in rows) or ("暂无" if user.language == "zh-CN" else "None")
        return TelegramMessage(
            ("⭐ 我的关注\n\n" if user.language == "zh-CN" else "⭐ Watchlist\n\n") + symbols,
            callback_keyboard([
                [("➕ 添加股票" if user.language == "zh-CN" else "➕ Add Symbol", "watchlist:add")],
                [("返回" if user.language == "zh-CN" else "Back", "more")],
            ]),
        )

    def _add_watchlist_symbol(
        self, user: TelegramRuntimeUser, raw_symbol: str,
    ) -> TelegramMessage:
        symbol = str(raw_symbol or "").upper().replace("US.", "").strip()
        portfolios = PortfolioService(self.db)
        portfolio = portfolios.get_default(user.telegram_user_id)
        if portfolio is None:
            portfolio = portfolios.create_portfolio(
                user.telegram_user_id, "Telegram Watchlist", is_default=True,
            )
        try:
            WatchlistService(self.db).add_symbol(
                portfolio.id, symbol, market="US", owner_id=user.telegram_user_id,
            )
        except DuplicateSymbol:
            return TelegramMessage(
                "%s 已在关注列表。" % symbol if user.language == "zh-CN" else
                "%s is already on your watchlist." % symbol,
                callback_keyboard([[
                    ("返回我的关注" if user.language == "zh-CN" else "Back to Watchlist", "watchlist"),
                ]]),
            )
        except ValidationError:
            return TelegramMessage(
                "股票代码无效，请重新添加。" if user.language == "zh-CN" else
                "Invalid stock symbol. Please try again.",
                callback_keyboard([[
                    ("重新添加" if user.language == "zh-CN" else "Try Again", "watchlist:add"),
                ]]),
            )
        return self._watchlist(user)

    def _holdings(self, user: TelegramRuntimeUser) -> TelegramMessage:
        rows = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.status == "OPEN",
        ).order_by(desc(SystemPaperPosition.open_time)).limit(10)))
        title = "📊 当前系统模拟持仓" if user.language == "zh-CN" else "📊 Open System Paper Positions"
        lines = ["%s %s @ %s" % (row.symbol, row.direction, row.current_price) for row in rows]
        return TelegramMessage(title + "\n\n" + ("\n".join(lines) or ("暂无" if user.language == "zh-CN" else "None")))

    def _history(self, user: TelegramRuntimeUser) -> TelegramMessage:
        rows = list(self.db.scalars(select(CompanionAnalysis).where(
            CompanionAnalysis.user_id == user.telegram_user_id,
        ).order_by(desc(CompanionAnalysis.created_at)).limit(5)))
        title = "🕘 历史分析" if user.language == "zh-CN" else "🕘 Analysis History"
        lines = ["#%s %s %s" % (row.id, row.context_type, row.status) for row in rows]
        return TelegramMessage(title + "\n\n" + ("\n".join(lines) or ("暂无" if user.language == "zh-CN" else "None")))

    def _reviews(self, user: TelegramRuntimeUser) -> TelegramMessage:
        rows = list(self.db.scalars(select(TradeReview).where(
            TradeReview.review_type == "SYSTEM",
        ).order_by(desc(TradeReview.review_time), desc(TradeReview.id)).limit(5)))
        title = "📝 系统交易复盘" if user.language == "zh-CN" else "📝 System Trade Reviews"
        lines = ["#%s %s %s" % (row.id, row.strategy_name or "-", row.result) for row in rows]
        return TelegramMessage(title + "\n\n" + ("\n".join(lines) or ("暂无" if user.language == "zh-CN" else "None")))

    def _notify_admins(
        self, profile: TelegramBotProfile, feedback: TelegramFeedbackRecord,
        user: TelegramRuntimeUser,
    ) -> None:
        admins = self._bound_admins()
        text = "Trade Companion Feedback\nCategory: %s\nUser ID: %s\nMessage: %s" % (
            feedback.category, user.telegram_user_id, feedback.message[:2000],
        )
        success = False
        for admin in admins:
            try:
                self.transport.send_message(
                    profile.token,
                    TelegramMessage(html.escape(text, quote=False)).as_payload(admin.telegram_user_id),
                )
                success = True
            except Exception:
                continue
        feedback.admin_notified = success
        self.db.commit()

    def _notify_admin_event(
        self, profile: TelegramBotProfile, event_type: str, message: str,
    ) -> bool:
        admins = self._bound_admins()
        success = False
        for admin in admins:
            try:
                self.transport.send_message(profile.token, TelegramMessage(
                    html.escape(
                        "Trade Companion Admin Alert\nEvent: %s\n%s" % (
                            event_type, message[:1000],
                        ),
                        quote=False,
                    ),
                ).as_payload(admin.telegram_user_id))
                self.db.add(TelegramRuntimeMessageLog(
                    bot_alias=profile.alias, direction="OUTBOUND",
                    event_type=event_type, chat_id=admin.telegram_user_id,
                    status="SUCCESS", payload_summary_json={"admin_alert": True},
                ))
                success = True
            except Exception:
                continue
        self.db.commit()
        return success

    def _bound_admins(self) -> List[TelegramAdminRecord]:
        rows = list(self.db.scalars(select(TelegramAdminRecord).where(
            TelegramAdminRecord.enabled.is_(True),
            TelegramAdminRecord.telegram_user_id.is_not(None),
        ).order_by(TelegramAdminRecord.id)))
        seen = set()
        result = []
        for row in rows:
            recipient = str(row.telegram_user_id or "")
            if recipient and recipient not in seen:
                seen.add(recipient)
                result.append(row)
        return result

    def log_message(
        self, profile: TelegramBotProfile, direction: str, event_type: str,
        status: str, chat_id: Optional[str] = None, update_id: Optional[str] = None,
        latency_ms: Optional[int] = None, error_code: Optional[str] = None,
    ) -> None:
        self.db.add(TelegramRuntimeMessageLog(
            bot_alias=profile.alias, direction=direction, event_type=event_type,
            chat_id=chat_id, update_id=update_id, status=status,
            latency_ms=latency_ms, error_code=error_code,
            error_message=None, payload_summary_json={},
        ))
        self.db.commit()
