import math
from typing import List

import pandas as pd


class FeatureQualityService:
    def validate_output(self, feature_name: str, series: pd.Series) -> List[str]:
        issues = []
        finite = series.dropna()
        if any(not math.isfinite(float(value)) for value in finite if not isinstance(value, str)):
            issues.append("OUTPUT_NOT_FINITE")
        if feature_name == "rsi_14" and ((finite < 0).any() or (finite > 100).any()):
            issues.append("OUTPUT_OUT_OF_RANGE")
        if feature_name == "atr_14" and (finite < 0).any():
            issues.append("OUTPUT_OUT_OF_RANGE")
        if feature_name == "volume_ratio_20" and (finite < 0).any():
            issues.append("OUTPUT_OUT_OF_RANGE")
        return issues

    @staticmethod
    def validate_alignment(target: pd.DataFrame, reference: pd.DataFrame) -> List[str]:
        if not target.index.is_monotonic_increasing or not reference.index.is_monotonic_increasing:
            return ["TIME_ALIGNMENT_ERROR"]
        return []

