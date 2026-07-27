from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from app.core.enums import BarInterval, FeatureQualityStatus, FeatureValueType


@dataclass(frozen=True)
class FeatureDefinition:
    feature_name: str
    display_name_zh: str
    category: str
    description: str
    value_type: FeatureValueType = FeatureValueType.DECIMAL
    default_parameters: Optional[Dict[str, Any]] = None
    required_bars: int = 1
    supported_intervals: tuple = tuple(item.value for item in BarInterval)
    requires_reference_symbol: bool = False
    reference_symbol: Optional[str] = None
    version: str = "1.0.0"


@dataclass
class FeatureValue:
    symbol: str
    interval: BarInterval
    timestamp_utc: datetime
    feature_name: str
    feature_version: str
    parameters_hash: str
    value: Union[Decimal, int, bool, str, None]
    value_type: FeatureValueType
    quality_status: FeatureQualityStatus
    quality_message: Optional[str]
    source_bar_timestamp: datetime
    data_source: str
