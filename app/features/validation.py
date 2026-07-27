from typing import List

import pandas as pd


def validate_input_bars(frame: pd.DataFrame) -> List[str]:
    issues = []
    if frame.index.has_duplicates:
        issues.append("DUPLICATE_INPUT")
    if not frame.index.is_monotonic_increasing:
        issues.append("TIME_ALIGNMENT_ERROR")
    if not frame.empty:
        invalid = (
            (frame["high"] < frame["low"]) |
            (frame["high"] < frame["open"]) |
            (frame["high"] < frame["close"]) |
            (frame["low"] > frame["open"]) |
            (frame["low"] > frame["close"]) |
            (frame["volume"] < 0)
        )
        if invalid.any():
            issues.append("INPUT_INVALID")
    return issues
