import importlib
import importlib.metadata
import logging
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


def mask_account_id(account_id: Any) -> str:
    value = str(account_id)
    return "****" + value[-4:] if len(value) >= 4 else "****"


@dataclass
class ConnectionCheckResult:
    success: bool
    status_code: str
    message_zh: str
    detail: str = ""


@dataclass
class MoomooCapabilityReport:
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    enabled: bool = False
    opend_reachable: bool = False
    opend_logged_in: bool = False
    sdk_available: bool = False
    sdk_version: str = ""
    opend_version: str = ""
    quote_context_available: bool = False
    us_quote_available: bool = False
    snapshot_available: bool = False
    historical_kline_available: bool = False
    market_state_available: bool = False
    paper_account_found: bool = False
    live_account_found: bool = False
    order_submission_enabled: bool = False
    live_trading_enabled: bool = False
    symbol_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    masked_accounts: List[Dict[str, str]] = field(default_factory=list)
    status_code: str = "not_checked"
    status_message_zh: str = "尚未检查"
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def safe_dict(self, include_masked_accounts: bool = False) -> Dict[str, Any]:
        data = asdict(self)
        if not include_masked_accounts:
            data.pop("masked_accounts", None)
        data["order_submission_enabled"] = False
        data["live_trading_enabled"] = False
        return data


class MoomooConnectionManager:
    """有限、只读、显式触发的OpenD连接生命周期管理器。"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        timeout: float = 10.0,
        sdk_loader: Optional[Callable[[], Any]] = None,
        socket_connector: Optional[Callable[..., Any]] = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sdk_loader = sdk_loader or (lambda: importlib.import_module("moomoo"))
        self._socket_connector = socket_connector or socket.create_connection
        self._contexts: List[Any] = []

    def sdk_version(self) -> str:
        try:
            return importlib.metadata.version("moomoo-api")
        except importlib.metadata.PackageNotFoundError:
            return ""

    def check_opend_socket(self) -> ConnectionCheckResult:
        try:
            connection = self._socket_connector((self.host, self.port), timeout=self.timeout)
            connection.close()
            return ConnectionCheckResult(True, "connected", "OpenD Socket连接成功")
        except socket.timeout as exc:
            return ConnectionCheckResult(False, "timeout", "OpenD连接请求超时", type(exc).__name__)
        except OSError as exc:
            return ConnectionCheckResult(False, "unreachable", "OpenD不可达", type(exc).__name__)

    def _sdk(self):
        sdk = self._sdk_loader()
        sdk_logger = getattr(sdk, "logger", None)
        if sdk_logger is not None and hasattr(sdk_logger, "console_level"):
            sdk_logger.console_level = logging.WARNING
        return sdk

    def open_quote_context(self):
        sdk = self._sdk()
        context = sdk.OpenQuoteContext(host=self.host, port=self.port)
        self._contexts.append(context)
        return context

    def open_us_trade_context(self):
        sdk = self._sdk()
        context = sdk.OpenSecTradeContext(
            filter_trdmarket=sdk.TrdMarket.US,
            host=self.host,
            port=self.port,
        )
        self._contexts.append(context)
        return context

    def close_all(self) -> None:
        while self._contexts:
            context = self._contexts.pop()
            try:
                context.close()
            except Exception:
                pass

    @staticmethod
    def _rows(data: Any) -> List[Dict[str, Any]]:
        if hasattr(data, "to_dict"):
            return list(data.to_dict("records"))
        if isinstance(data, list):
            return data
        return []

    def inspect(self, symbols: Optional[List[str]] = None, enabled: bool = True) -> MoomooCapabilityReport:
        symbols = symbols or ["US.QQQ", "US.SOXL"]
        report = MoomooCapabilityReport(enabled=enabled)
        report.sdk_version = self.sdk_version()
        report.sdk_available = bool(report.sdk_version)
        if not report.sdk_available:
            report.status_code = "sdk_missing"
            report.status_message_zh = "Moomoo SDK未安装"
            report.errors.append("请在项目虚拟环境安装moomoo-api。")
            return report

        socket_result = self.check_opend_socket()
        report.opend_reachable = socket_result.success
        if not socket_result.success:
            report.status_code = socket_result.status_code
            report.status_message_zh = socket_result.message_zh
            report.errors.append(socket_result.message_zh)
            return report

        try:
            sdk = self._sdk()
        except Exception as exc:
            report.status_code = "sdk_error"
            report.status_message_zh = "Moomoo SDK加载异常"
            report.errors.append("SDK异常：" + type(exc).__name__)
            return report

        quote_context = None
        trade_context = None
        try:
            quote_context = self.open_quote_context()
            report.quote_context_available = True
            ret, state = quote_context.get_global_state()
            if ret == sdk.RET_OK:
                report.opend_logged_in = True
                if hasattr(state, "get"):
                    report.opend_version = str(
                        state.get("server_ver", state.get("server_version", ""))
                    )
            else:
                report.warnings.append("OpenD未登录或全局状态读取失败。")

            ret, market_data = quote_context.get_market_state(symbols)
            report.market_state_available = ret == sdk.RET_OK
            if ret != sdk.RET_OK:
                report.warnings.append("市场状态读取失败：" + str(market_data))

            for symbol in symbols:
                result = {
                    "基础报价": False,
                    "快照": False,
                    "历史K线": False,
                    "状态": "未检查",
                }
                ret, snapshot = quote_context.get_market_snapshot([symbol])
                if ret == sdk.RET_OK:
                    result["快照"] = True
                    result["基础报价"] = True
                    result["状态"] = "成功"
                    report.snapshot_available = True
                    report.us_quote_available = True
                else:
                    result["状态"] = self._classify_quote_error(snapshot)
                    report.warnings.append(symbol + "：" + result["状态"])
                ret, history, _ = quote_context.request_history_kline(symbol, max_count=1)
                if ret == sdk.RET_OK:
                    result["历史K线"] = True
                    report.historical_kline_available = True
                elif result["状态"] == "成功":
                    result["状态"] = self._classify_quote_error(history)
                report.symbol_results[symbol] = result

            trade_context = self.open_us_trade_context()
            ret, accounts = trade_context.get_acc_list()
            if ret == sdk.RET_OK:
                for row in self._rows(accounts):
                    environment = str(row.get("trd_env", "")).upper()
                    is_paper = "SIMULATE" in environment
                    is_live = "REAL" in environment
                    report.paper_account_found = report.paper_account_found or is_paper
                    report.live_account_found = report.live_account_found or is_live
                    report.masked_accounts.append(
                        {
                            "账户标识": mask_account_id(row.get("acc_id", "")),
                            "市场": str(row.get("trd_market", "US")),
                            "类型": "模拟账户" if is_paper else "真实账户" if is_live else "未知",
                            "状态": str(row.get("acc_status", "可用")),
                        }
                    )
            else:
                report.warnings.append("账户列表读取失败，但未进行任何交易操作。")

            report.status_code = "connected" if report.opend_logged_in else "not_logged_in"
            report.status_message_zh = (
                "OpenD连接和能力检查完成" if report.opend_logged_in else "OpenD可达但尚未登录"
            )
        except TimeoutError as exc:
            report.status_code = "timeout"
            report.status_message_zh = "OpenD请求超时"
            report.errors.append(type(exc).__name__)
        except Exception as exc:
            report.status_code = "sdk_error"
            report.status_message_zh = "Moomoo SDK请求异常"
            report.errors.append(type(exc).__name__)
        finally:
            self.close_all()
        report.order_submission_enabled = False
        report.live_trading_enabled = False
        return report

    @staticmethod
    def _classify_quote_error(value: Any) -> str:
        message = str(value).lower()
        if "permission" in message or "权限" in message or "no right" in message:
            return "权限不足"
        if "code" in message or "symbol" in message or "股票代码" in message:
            return "代码不支持"
        return "请求失败"


class MoomooConnectionChecker:
    """兼容Sprint 00脚本的只读包装器。"""

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self.manager = MoomooConnectionManager(host, port, timeout)

    def check_all(self) -> MoomooCapabilityReport:
        return self.manager.inspect()
