"""Historical comparison helpers for auditable QMR context validation."""
from statistics import median


def compare_context_variants(cases):
    """Compare already reconstructed outcomes; never reads future bars itself."""
    groups = {"BASELINE": [], "GLOBAL_GATE": [], "GLOBAL_SECTOR_GATE": []}
    for case in cases:
        result = float(case["return"])
        groups["BASELINE"].append(result)
        if case.get("global_state") not in {"RISK_OFF", "DATA_UNAVAILABLE"}:
            groups["GLOBAL_GATE"].append(result)
            if case.get("sector_state") not in {"VERY_WEAK", "DATA_UNAVAILABLE"}:
                groups["GLOBAL_SECTOR_GATE"].append(result)
    return {key: _metrics(values) for key, values in groups.items()}


def _metrics(values):
    if not values:
        return {"sample_count": 0, "win_rate": None, "average_return": None,
                "median_return": None}
    return {"sample_count": len(values),
            "win_rate": sum(value > 0 for value in values) / len(values),
            "average_return": sum(values) / len(values),
            "median_return": median(values)}
