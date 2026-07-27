import hashlib
import json
from copy import deepcopy
from typing import Dict

from app.strategy.constants import PARAMETER_STATUS

BASE_PARAMETERS = {
    "pullback_min_pct": 1.0,
    "pullback_max_pct": 5.0,
    "candidate_buy_threshold": 72,
    "volume_ratio_min": 1.0,
    "relative_strength_min": 0.0,
    "atr_pct_max": 4.0,
    "rsi_overbought": 75.0,
    "vwap_deviation_max_pct": 3.0,
    "close_position_min": 0.60,
    "body_ratio_max": 0.85,
    "parameter_status": PARAMETER_STATUS,
}

TEMPLATE_OVERRIDES = {
    "BROAD_MARKET": {"pullback_min_pct": 1.0, "pullback_max_pct": 3.0, "atr_pct_max": 2.5},
    "SECTOR_ETF": {"pullback_min_pct": 1.5, "pullback_max_pct": 4.0, "atr_pct_max": 3.5},
    "LEVERAGED_ETF": {"pullback_min_pct": 3.0, "pullback_max_pct": 8.0, "atr_pct_max": 8.0, "rsi_overbought": 80.0},
    "INVERSE_LEVERAGED_ETF": {"pullback_min_pct": 3.0, "pullback_max_pct": 8.0, "atr_pct_max": 9.0, "candidate_buy_threshold": 80},
    "HIGH_GROWTH": {"pullback_min_pct": 2.0, "pullback_max_pct": 6.0, "atr_pct_max": 6.0},
    "DEFAULT": {},
}

PARAMETER_TYPES = {
    key: (str if key == "parameter_status" else (int if key == "candidate_buy_threshold" else float))
    for key in BASE_PARAMETERS
}


def parameters_for_template(template: str) -> Dict[str, object]:
    values = deepcopy(BASE_PARAMETERS)
    values.update(TEMPLATE_OVERRIDES[template])
    return values


def parameters_hash(parameters: Dict[str, object]) -> str:
    raw = json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_parameter_update(current: Dict[str, object], updates: Dict[str, object]) -> Dict[str, object]:
    result = deepcopy(current)
    for key, raw in updates.items():
        if key not in PARAMETER_TYPES or key == "parameter_status":
            raise ValueError("未知或不可修改参数：" + key)
        expected = PARAMETER_TYPES[key]
        try:
            value = expected(raw)
        except (TypeError, ValueError):
            raise ValueError("参数类型错误：" + key)
        if key.endswith("_pct") or key.endswith("_min") or key.endswith("_max") or key == "volume_ratio_min":
            if float(value) < 0 or float(value) > 100:
                raise ValueError("参数超出允许范围：" + key)
        if key == "candidate_buy_threshold" and not 0 <= int(value) <= 100:
            raise ValueError("候选阈值必须在0到100之间")
        result[key] = value
    if result["pullback_min_pct"] > result["pullback_max_pct"]:
        raise ValueError("回撤最小值不得大于最大值")
    result["parameter_status"] = PARAMETER_STATUS
    return result
