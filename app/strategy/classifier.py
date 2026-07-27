from typing import Dict, Optional

from app.database.models import Instrument
from app.strategy.constants import KNOWN_CLASSIFICATIONS


class TickerClassifier:
    def classify(self, symbol: str, instrument: Optional[Instrument] = None) -> Dict[str, object]:
        known = KNOWN_CLASSIFICATIONS.get(symbol)
        if known:
            result = dict(known)
        else:
            result = {
                "asset_type": "UNKNOWN",
                "sector": "unknown",
                "role": "TRADING",
                "benchmark_symbol": "QQQ",
                "strategy_template": "DEFAULT",
            }
        if instrument and instrument.is_supported:
            status = "VALID"
            message = instrument.support_message or "本地证券主数据验证可用"
        elif instrument and instrument.support_status in {
            "INVALID", "INVALID_SYMBOL", "CODE_NOT_FOUND", "UNSUPPORTED",
        }:
            status = "INVALID"
            message = instrument.support_message or "本地证券主数据标记为不可用"
        else:
            status = "PENDING_VALIDATION"
            message = "OpenD不可用或无法完整确认资产类型，当前使用本地默认分类"
        result.update(
            display_name=instrument.display_name if instrument else "",
            validation_status=status,
            validation_message=message,
        )
        return result
