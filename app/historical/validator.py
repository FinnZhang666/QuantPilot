from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.data.providers.moomoo import MoomooConnectionManager
from app.historical.instruments import InstrumentService


class MoomooInstrumentValidator:
    """仅使用行情接口验证证券代码，不查询资金、持仓或交易能力。"""

    def __init__(self, manager: MoomooConnectionManager):
        self.manager = manager

    def validate(self, service: InstrumentService, instruments: List[Any]) -> None:
        context = None
        try:
            sdk = self.manager._sdk()
            context = self.manager.open_quote_context()
            for instrument in instruments:
                code = None
                ret, snapshot = context.get_market_snapshot([instrument.symbol])
                if ret != sdk.RET_OK:
                    code = self._find_exact_code(context, sdk, instrument.alias or instrument.code)
                    if code and code != instrument.symbol:
                        ret, snapshot = context.get_market_snapshot([code])
                    else:
                        service.set_validation(
                            instrument, False, "PENDING", "代码未确认：" + str(snapshot)[:120]
                        )
                        continue
                ret_h, history, _ = context.request_history_kline(
                    code or instrument.symbol,
                    start=(datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d"),
                    end=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    ktype=sdk.KLType.K_DAY,
                    autype=sdk.AuType.QFQ,
                    max_count=1,
                )
                if ret_h != sdk.RET_OK:
                    message = str(history)
                    status = "PERMISSION_DENIED" if "permission" in message.lower() else "UNSUPPORTED"
                    service.set_validation(instrument, False, status, message[:180])
                    continue
                rows = snapshot.to_dict("records") if hasattr(snapshot, "to_dict") else []
                info = rows[0] if rows else {}
                actual = str(info.get("code", instrument.symbol))
                info.setdefault("name", info.get("name", instrument.display_name))
                service.set_validation(
                    instrument, True, "SUPPORTED", "快照和历史K线可用", actual, info
                )
        finally:
            self.manager.close_all()

    @staticmethod
    def _find_exact_code(context: Any, sdk: Any, alias: str):
        candidates = []
        for security_type in (sdk.SecurityType.STOCK, sdk.SecurityType.ETF, sdk.SecurityType.IDX):
            ret, data = context.get_stock_basicinfo(sdk.Market.US, security_type)
            if ret != sdk.RET_OK or not hasattr(data, "to_dict"):
                continue
            candidates.extend(data.to_dict("records"))
        alias_upper = alias.upper()
        exact = [
            str(row.get("code"))
            for row in candidates
            if str(row.get("code", "")).split(".")[-1].upper() == alias_upper
        ]
        return exact[0] if len(exact) == 1 else None
