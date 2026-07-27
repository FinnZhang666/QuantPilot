from typing import Any, Callable, Dict, Iterable, List

from app.core.enums import RealtimeDataType
from app.data.providers.moomoo import MoomooConnectionManager
from app.realtime.normalizer import MoomooRealtimeNormalizer


class MoomooRealtimeProvider:
    def __init__(
        self,
        connection_manager: MoomooConnectionManager,
        on_data: Callable[[Any], None],
        normalizer: MoomooRealtimeNormalizer,
    ):
        self.connection_manager = connection_manager
        self.on_data = on_data
        self.normalizer = normalizer
        self.context = None
        self.handlers_registered = False
        self.on_error: Callable[[Exception], None] = lambda exc: None

    def connect(self) -> None:
        if self.context is not None:
            return
        socket = self.connection_manager.check_opend_socket()
        if not socket.success:
            raise ConnectionError(socket.message_zh)
        self.context = self.connection_manager.open_quote_context()
        self._register_handlers()

    def _register_handlers(self) -> None:
        sdk = self.connection_manager._sdk()
        provider = self

        class QuoteHandler(sdk.StockQuoteHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret, data = super().on_recv_rsp(rsp_pb)
                if ret == sdk.RET_OK:
                    try:
                        for item in provider.normalizer.quotes(data):
                            provider.on_data(item)
                    except Exception as exc:
                        provider.on_error(RuntimeError("QUOTE：" + str(exc)))
                return ret, data

        class TickerHandler(sdk.TickerHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret, data = super().on_recv_rsp(rsp_pb)
                if ret == sdk.RET_OK:
                    try:
                        for item in provider.normalizer.tickers(data):
                            provider.on_data(item)
                    except Exception as exc:
                        provider.on_error(RuntimeError("TICKER：" + str(exc)))
                return ret, data

        class KlineHandler(sdk.CurKlineHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret, data = super().on_recv_rsp(rsp_pb)
                if ret == sdk.RET_OK:
                    try:
                        for item in provider.normalizer.bars(data):
                            provider.on_data(item)
                    except Exception as exc:
                        provider.on_error(RuntimeError("KLINE_1M：" + str(exc)))
                return ret, data

        for handler in (QuoteHandler(), TickerHandler(), KlineHandler()):
            self.context.set_handler(handler)
        self.handlers_registered = True

    def type_map(self) -> Dict[RealtimeDataType, Any]:
        sdk = self.connection_manager._sdk()
        return {
            RealtimeDataType.QUOTE: sdk.SubType.QUOTE,
            RealtimeDataType.TICKER: sdk.SubType.TICKER,
            RealtimeDataType.KLINE_1M: sdk.SubType.K_1M,
        }

    def subscribe(self, symbols: Iterable[str], data_types: Iterable[RealtimeDataType]) -> Dict[str, str]:
        if self.context is None:
            raise RuntimeError("实时行情Context尚未连接")
        sdk = self.connection_manager._sdk()
        failures = {}
        mapping = self.type_map()
        for symbol in symbols:
            for data_type in data_types:
                if data_type == RealtimeDataType.MARKET_STATE:
                    continue
                ret, message = self.context.subscribe([symbol], [mapping[data_type]], is_first_push=True, subscribe_push=True)
                if ret != sdk.RET_OK:
                    failures[symbol + ":" + data_type.value] = str(message)
        return failures

    def unsubscribe(self, symbols: Iterable[str], data_types: Iterable[RealtimeDataType]) -> Dict[str, str]:
        if self.context is None:
            return {}
        sdk = self.connection_manager._sdk()
        failures = {}
        mapping = self.type_map()
        for symbol in symbols:
            for data_type in data_types:
                if data_type == RealtimeDataType.MARKET_STATE:
                    continue
                ret, message = self.context.unsubscribe([symbol], [mapping[data_type]], unsubscribe_all=False)
                if ret != sdk.RET_OK:
                    failures[symbol + ":" + data_type.value] = str(message)
        return failures

    def market_state(self, symbols: List[str]) -> Any:
        if self.context is None:
            return None
        sdk = self.connection_manager._sdk()
        ret, data = self.context.get_market_state(symbols)
        return data if ret == sdk.RET_OK else None

    def close(self) -> None:
        self.connection_manager.close_all()
        self.context = None
        self.handlers_registered = False
