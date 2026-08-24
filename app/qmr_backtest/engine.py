import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from statistics import mean, median

from app.buy_score.scoring import STATUS_ORDER
from app.qmr_backtest.metrics import summarize, target_stop_path, trailing_stop_path
from app.qmr_exit.backtest import comparison_paths


class QmrBacktestEngine:
    def __init__(self, config, recovery_config=None, exit_config=None):
        self.config = config
        self.recovery_config = recovery_config or {}
        self.exit_config = exit_config

    def events(self, rows):
        reached = defaultdict(set)
        for score, instrument in rows:
            for level in self.config["entry_levels"]:
                if STATUS_ORDER.get(score.buy_status, -1) < STATUS_ORDER[level]:
                    reached[score.symbol].discard(level)
                    continue
                if level in reached[score.symbol]:
                    continue
                reached[score.symbol].add(level)
                yield score, instrument, level

    def evaluate(self, run_id, score, instrument, level, bars):
        signal_time = score.evaluation_time
        future = [bar for bar in bars if bar.timestamp_utc > signal_time]
        previous = [bar for bar in bars if bar.timestamp_utc <= signal_time]
        if not future:
            return None
        entry = float(future[0].open)
        periods = self.config["holding_periods"]
        returns, mfe, mae = {}, {}, {}
        for period in periods:
            window = future[:period]
            key = "%sd" % period
            if len(window) < period:
                returns[key] = mfe[key] = mae[key] = None
                continue
            returns[key] = (float(window[-1].close) / entry - 1) * 100
            mfe[key] = (max(float(bar.high) for bar in window) / entry - 1) * 100
            mae[key] = (min(float(bar.low) for bar in window) / entry - 1) * 100
        local_window = previous[-self.config["local_bottom_window_days"]:] + future[:self.config["local_bottom_window_days"]]
        local_bottom = min((float(bar.low) for bar in local_window), default=None)
        distance = (entry / local_bottom - 1) * 100 if local_bottom else None
        maximum = future[:max(periods)]
        matrix = {}
        for stop in self.config["stops_pct"]:
            for target in self.config["targets_pct"]:
                matrix["stop_%s_target_%s" % (stop, target)] = target_stop_path(
                    maximum, entry, target, stop, self.config["same_bar_policy"])
        trailing = {str(value): trailing_stop_path(maximum, entry, value)
                    for value in self.config["trailing_stops_pct"]}
        result = self._result(returns, mae)
        snapshot = dict(score.score_components_json or {})
        snapshot["recovery_snapshot"] = getattr(score, "_qmr_backtest_recovery_snapshot", {})
        if self.exit_config:
            snapshot["exit_comparison"] = comparison_paths(maximum, entry, self.exit_config)
        failures = self._failure_features(score, returns, mae, snapshot)
        return {
            "run_id": run_id, "buy_score_id": score.id,
            "event_key": "QMR-%s-%08d-%s" % (signal_time.year, score.id, level),
            "symbol": score.symbol, "entry_level": level, "signal_time": signal_time,
            "signal_price": entry, "quality_score": score.quality_score,
            "mispricing_score": score.mispricing_score, "recovery_score": score.recovery_score,
            "buy_score": score.final_buy_score, "buy_grade": score.buy_grade,
            "market_state": snapshot.get("market_state") or getattr(score, "_qmr_backtest_market_state", None),
            "sector": instrument.sector, "data_confidence": score.data_confidence,
            "result": result, "local_bottom_price": local_bottom,
            "signal_vs_local_bottom": distance,
            "consecutive_down_days": self._consecutive_down(previous),
            "returns_json": returns, "mfe_json": mfe, "mae_json": mae,
            "target_stop_json": matrix, "trailing_stop_json": trailing,
            "feature_snapshot_json": json.loads(json.dumps(snapshot, default=str)),
            "failure_features_json": failures,
        }

    @staticmethod
    def _result(returns, mae):
        final = returns.get("20d")
        adverse = mae.get("20d")
        if final is None:
            return "INSUFFICIENT_DATA"
        if adverse is not None and adverse <= -10:
            return "FALSE_RECOVERY" if final < 0 else "STOPPED"
        return "SUCCESS" if final > 0 else "FAILURE"

    @staticmethod
    def _consecutive_down(previous):
        count = 0
        for bar in reversed(previous):
            if float(bar.close) < float(bar.open): count += 1
            else: break
        return count

    @staticmethod
    def _failure_features(score, returns, mae, snapshot):
        if (returns.get("20d") or 0) >= 0:
            return []
        items = []
        risk = snapshot.get("risk", {})
        for key, value in risk.items():
            if isinstance(value, dict) and value.get("penalty", 0) > 0: items.append(key)
        if score.data_confidence != "HIGH": items.append("data_confidence_%s" % score.data_confidence.lower())
        if (mae.get("5d") or 0) <= -10: items.append("early_large_adverse_move")
        return sorted(set(items))

    def aggregate(self, cases):
        records = [self.to_dict(case) for case in cases]
        slices = []
        dimensions = {
            "ALL": lambda item: "ALL", "ENTRY_LEVEL": lambda item: item["entry_level"],
            "YEAR": lambda item: str(item["signal_time"].year),
            "SECTOR": lambda item: item["sector"] or "UNKNOWN",
            "BUY_SCORE": lambda item: self.score_bucket(item["buy_score"]),
            "GRADE": lambda item: item["buy_grade"],
            "MARKET_STATE": lambda item: item["market_state"] or "UNKNOWN",
            "DRAWDOWN": lambda item: self.drawdown_bucket(item),
            "DOWN_DAYS": lambda item: "5+" if (item["consecutive_down_days"] or 0) >= 5 else str(item["consecutive_down_days"] or 0),
        }
        for dimension, selector in dimensions.items():
            groups = defaultdict(list)
            for item in records: groups[selector(item)].append(item)
            for value, members in groups.items():
                for period in self.config["holding_periods"]:
                    metrics = summarize([item["returns_json"].get("%sd" % period) for item in members])
                    metrics["average_mfe"] = self.optional_mean(item["mfe_json"].get("%sd" % period) for item in members)
                    metrics["average_mae"] = self.optional_mean(item["mae_json"].get("%sd" % period) for item in members)
                    slices.append({"dimension": dimension, "dimension_value": value,
                        "holding_period": period, "sample_count": metrics["sample_count"],
                        "confidence_level": metrics["confidence_level"], "metrics_json": metrics})
        return slices

    def summary(self, cases):
        rows = [self.to_dict(case) for case in cases]
        periods = {}
        for period in self.config["holding_periods"]:
            periods[str(period)] = summarize([row["returns_json"].get("%sd" % period) for row in rows])
        bottoms = [row["signal_vs_local_bottom"] for row in rows if row["signal_vs_local_bottom"] is not None]
        bottom = summarize(bottoms)
        matrix = self.matrix_summary(rows)
        best_period = self.best_period(periods)
        result_counts = defaultdict(int)
        level_counts = defaultdict(int)
        for row in rows:
            result_counts[row["result"]] += 1; level_counts[row["entry_level"]] += 1
        return {"sample_count": len(rows), "entry_levels": dict(level_counts),
            "results": dict(result_counts), "holding_periods": periods,
            "bottom_capture": bottom, "best_holding_period": best_period,
            "target_stop_matrix": matrix, "best_target_stop": self.best_matrix(matrix),
            "trailing_stops": self.trailing_summary(rows),
            "best_entry_level": self.best_entry_level(rows),
            "grade_calibration": self.grade_calibration(rows),
            "factor_ablation": self.failure_factor_summary(rows),
            "exit_engine_comparison": self.exit_comparison(rows)}

    @staticmethod
    def exit_comparison(rows):
        keys = ("fixed_5d", "fixed_10d")
        result = {key: summarize([row["feature_snapshot_json"].get("exit_comparison", {}).get(key)
                                  for row in rows]) for key in keys}
        engine = [row["feature_snapshot_json"].get("exit_comparison", {}).get("qmr_exit_engine", {})
                  for row in rows]
        result["qmr_exit_engine"] = summarize([item.get("realized_return") for item in engine])
        result["qmr_exit_engine"]["average_captured_mfe_ratio"] = QmrBacktestEngine.optional_mean(
            item.get("captured_mfe_ratio") for item in engine)
        result["qmr_exit_engine"]["average_giveback"] = QmrBacktestEngine.optional_mean(
            item.get("profit_giveback") for item in engine)
        return result

    def matrix_summary(self, rows):
        keys = {key for row in rows for key in row["target_stop_json"]}
        output = {}
        for key in sorted(keys):
            outcomes = [row["target_stop_json"][key] for row in rows
                        if row["target_stop_json"].get(key, {}).get("return_pct") is not None]
            values = [outcome["return_pct"] for outcome in outcomes]
            output[key] = summarize(values)
            output[key]["target_before_stop_rate"] = (
                sum(outcome["outcome"] == "TARGET" for outcome in outcomes) / len(outcomes)
                if outcomes else None)
            output[key]["equity_max_drawdown"] = self.sequence_drawdown(values)
        return output

    def trailing_summary(self, rows):
        keys = {key for row in rows for key in row["trailing_stop_json"]}
        return {key: summarize([row["trailing_stop_json"][key]["return_pct"] for row in rows
            if row["trailing_stop_json"].get(key, {}).get("return_pct") is not None]) for key in sorted(keys)}

    def failure_factor_summary(self, rows):
        counts = defaultdict(int)
        failures = [row for row in rows if row["result"] in ("FAILURE", "FALSE_RECOVERY", "STOPPED")]
        for row in failures:
            for factor in row["failure_features_json"]: counts[factor] += 1
        factors = {
            "higher_low": ("stabilization", "higher_low"),
            "vwap_reclaim": ("stabilization", "vwap_recovery"),
            "rvol": ("capital_flow", "rvol"),
            "up_down_volume": ("capital_flow", "up_down_volume"),
            "macd": ("technical", "macd"), "rsi_recovery": ("technical", "rsi"),
            "sector_recovery": ("sector", "score"), "market_recovery": ("market", "score"),
        }
        comparison = {}
        for name, path in factors.items():
            present, absent = [], []
            for row in rows:
                recovery = row["feature_snapshot_json"].get("recovery_snapshot", {})
                component = recovery.get(path[0], {}).get(path[1])
                available = component is not None and (not isinstance(component, dict) or component.get("available", True))
                value = row["returns_json"].get("20d")
                (present if available else absent).append(value)
            comparison[name] = {"factor_available": summarize(present), "factor_missing": summarize(absent)}
        return {"method": "EXISTING_EVENT_FACTOR_AVAILABILITY_ABLATION",
                "limitation": "Does not regenerate events excluded by the historical model.",
                "failed_samples": len(failures), "failure_factor_counts": dict(sorted(counts.items())),
                "comparisons": comparison}

    @staticmethod
    def sequence_drawdown(returns):
        equity = peak = 1.0
        maximum = 0.0
        for value in returns:
            equity *= 1 + float(value) / 100
            peak = max(peak, equity)
            maximum = min(maximum, equity / peak - 1)
        return maximum * 100

    @staticmethod
    def best_entry_level(rows):
        groups = defaultdict(list)
        for row in rows: groups[row["entry_level"]].append(row["returns_json"].get("20d"))
        metrics = {key: summarize(values) for key, values in groups.items()}
        ranked = [(value.get("profit_factor") or 0, value.get("expectancy") or -999, key)
                  for key, value in metrics.items() if value["sample_count"]]
        return {"level": max(ranked)[2] if ranked else None, "metrics": metrics}

    @staticmethod
    def grade_calibration(rows):
        groups = defaultdict(list)
        for row in rows: groups[row["buy_grade"]].append(row["returns_json"].get("5d"))
        averages = {grade: summarize(values) for grade, values in groups.items()}
        sequence = [averages[grade]["average_return"] for grade in ("S", "A", "B", "C")
                    if grade in averages and averages[grade]["average_return"] is not None]
        return {"metrics": averages,
                "monotonic": len(sequence) > 1 and all(sequence[i] >= sequence[i + 1]
                                                        for i in range(len(sequence) - 1))}

    @staticmethod
    def best_period(periods):
        candidates = [(value.get("profit_factor") or 0, value.get("positive_rate") or 0,
                       value.get("average_return") or -999, period)
                      for period, value in periods.items() if value["sample_count"]]
        return int(max(candidates)[3]) if candidates else None

    @staticmethod
    def best_matrix(matrix):
        candidates = [(value.get("profit_factor") or 0, value.get("expectancy") or -999, key)
                      for key, value in matrix.items() if value["sample_count"]]
        return max(candidates)[2] if candidates else None

    @staticmethod
    def optional_mean(values):
        clean = [float(value) for value in values if value is not None]
        return mean(clean) if clean else None

    @staticmethod
    def score_bucket(score):
        if score >= 90: return "90-100"
        if score >= 80: return "80-89"
        if score >= 70: return "70-79"
        if score >= 60: return "60-69"
        return "<60"

    @staticmethod
    def drawdown_bucket(item):
        values = item["feature_snapshot_json"].get("inputs", {})
        value = values.get("mispricing")
        return "UNKNOWN" if value is None else QmrBacktestEngine.score_bucket(value)

    @staticmethod
    def to_dict(case):
        if isinstance(case, dict): return case
        return {column.name: getattr(case, column.name) for column in case.__table__.columns}
