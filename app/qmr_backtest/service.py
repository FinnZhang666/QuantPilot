import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from app.qmr_backtest.engine import QmrBacktestEngine
from app.qmr_backtest.metrics import summarize
from app.qmr_backtest.repository import QmrBacktestRepository


class QmrBacktestService:
    def __init__(self, db, settings, config_path=None):
        self.db, self.settings = db, settings
        self.config = yaml.safe_load(Path(config_path or settings.qmr_backtest_config_file).read_text(encoding="utf-8"))
        self.recovery_config = yaml.safe_load(Path(settings.recovery_config_file).read_text(encoding="utf-8"))
        self.repository = QmrBacktestRepository(db)
        self.engine = QmrBacktestEngine(self.config, self.recovery_config)

    def prepare(self, start, end, parameter_name="default", symbols=None, dry_run=False):
        start, end = self.utc(start), self.utc(end)
        if start >= end: raise ValueError("开始时间必须早于结束时间。")
        symbols = sorted({item.upper().replace("US.", "") for item in (symbols or [])})
        estimate = self.estimate_storage(start, end, len(symbols) or 500)
        payload = {"parameters": self.config, "start": start.isoformat(), "end": end.isoformat(), "symbols": symbols}
        run_key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        if dry_run:
            return {"dry_run": True, "run_id": None, "estimated_storage_bytes": estimate,
                    "warnings": ["历史Universe有效期将在正式运行时检查。"]}
        config_hash = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()
        parameter = self.repository.parameter_set(parameter_name, self.config["strategy_version"], config_hash, self.config)
        run = self.repository.create_run(parameter, run_key, start, end,
            self.config["source_buy_score_version"], symbols, estimate)
        return {"dry_run": False, "run_id": run.id, "status": run.status,
                "estimated_storage_bytes": estimate}

    def execute(self, run_id):
        run = self.db.get(__import__("app.database.models", fromlist=["QmrBacktestRun"]).QmrBacktestRun, run_id)
        if run is None: raise ValueError("QMR回测任务不存在。")
        if run.status not in ("PENDING", "FAILED"): return self.serialize_run(run)
        now = datetime.now(timezone.utc); self.repository.mark_running(run, now)
        warnings, cases = [], []
        try:
            universe = self.repository.historical_universe_coverage(self.utc(run.data_start), self.utc(run.data_end))
            warnings.append(universe["warning"])
            if (self.utc(run.data_end) - self.utc(run.data_start)).days < 365 * 5:
                warnings.append("请求区间少于5年，只能作为流程或短周期研究结果。")
            rows = self.repository.signals(run.data_start, run.data_end, run.model_version, run.symbols_json or None)
            coverage = self.repository.data_coverage(rows); coverage["universe"] = universe
            events = list(self.engine.events(rows))
            for index, (score, instrument, level) in enumerate(events):
                self.db.refresh(run)
                if run.cancel_requested:
                    self.repository.finish(run, "CANCELLED", "RESEARCH", {}, coverage, warnings,
                                           datetime.now(timezone.utc)); return self.serialize_run(run)
                if self.repository.case_exists(run.id, score.id, level): continue
                signal_time = self.utc(score.evaluation_time)
                bars = self.repository.bars(score.symbol,
                    signal_time - timedelta(days=self.config["local_bottom_window_days"] * 3),
                    signal_time + timedelta(days=max(self.config["holding_periods"]) * 3),
                    self.config["timeframe"])
                values = self.engine.evaluate(run.id, score, instrument, level, bars)
                if values is not None: cases.append(self.repository.save_case(values))
                if index % 50 == 0:
                    self.db.commit(); self.repository.update_progress(run, int(80 * (index + 1) / max(1, len(events))))
            self.db.commit(); cases = self.repository.cases(run.id)
            for values in self.engine.aggregate(cases):
                values["run_id"] = run.id; self.repository.save_result(values)
            self._walk_forward(run, cases)
            summary = self.engine.summary(cases)
            summary["point_in_time_validation"] = self.point_in_time_validation(run, cases)
            summary["walk_forward"] = self._walk_forward_summary(cases)
            strategy_status = self.strategy_status(summary, universe)
            self.repository.finish(run, "SUCCESS", strategy_status, summary, coverage, warnings,
                                   datetime.now(timezone.utc))
            return self.serialize_run(run)
        except Exception as exc:
            self.db.rollback()
            self.repository.finish(run, "FAILED", "RESEARCH", {}, {}, warnings,
                datetime.now(timezone.utc), "%s: %s" % (type(exc).__name__, str(exc)[:500]))
            raise

    def _walk_forward(self, run, cases):
        years = sorted({self.utc(case.signal_time).year for case in cases})
        minimum = self.config["walk_forward"]["minimum_training_years"]
        fold = 0
        for test_year in years[minimum:]:
            train = [case for case in cases if self.utc(case.signal_time).year < test_year]
            test = [case for case in cases if self.utc(case.signal_time).year == test_year]
            if not train or not test: continue
            fold += 1
            self.repository.save_fold({"run_id": run.id, "fold_number": fold,
                "training_start": min(self.utc(case.signal_time) for case in train),
                "training_end": max(self.utc(case.signal_time) for case in train),
                "test_start": min(self.utc(case.signal_time) for case in test),
                "test_end": max(self.utc(case.signal_time) for case in test),
                "parameter_set_id": run.parameter_set_id,
                "in_sample_json": self._period_metric(train, 20),
                "out_of_sample_json": self._period_metric(test, 20)})
        self.db.commit()

    def _walk_forward_summary(self, cases):
        years = sorted({self.utc(case.signal_time).year for case in cases})
        if len(years) < 2: return {"status": "INSUFFICIENT_YEARS", "in_sample": {}, "out_of_sample": {}}
        split = years[-1]
        return {"status": "AVAILABLE", "test_year": split,
            "in_sample": self._period_metric([c for c in cases if self.utc(c.signal_time).year < split], 20),
            "out_of_sample": self._period_metric([c for c in cases if self.utc(c.signal_time).year == split], 20)}

    @staticmethod
    def _period_metric(cases, period):
        return summarize([case.returns_json.get("%sd" % period) for case in cases])

    @staticmethod
    def point_in_time_validation(run, cases):
        violations = [case.id for case in cases if case.signal_time < run.data_start or case.signal_time > run.data_end]
        return {"passed": not violations, "violations": violations,
                "rule": "signal inputs persisted at timestamp; outcome bars strictly after signal"}

    def strategy_status(self, summary, universe):
        test = summary.get("walk_forward", {}).get("out_of_sample", {})
        rules = self.config["validation"]
        if universe["status"] != "AVAILABLE": return "RESEARCH"
        if summary["sample_count"] < rules["minimum_samples"]: return "RESEARCH"
        if rules["require_positive_out_of_sample"] and (test.get("average_return") or 0) <= 0: return "REJECTED"
        if (test.get("profit_factor") or 0) <= rules["minimum_profit_factor"]: return "REJECTED"
        return "VALIDATED"

    @staticmethod
    def estimate_storage(start, end, symbols):
        years = max(1, (end - start).days / 365.25)
        return int(symbols * years * 3 * 3500)

    def get(self, run_id):
        from app.database.models import QmrBacktestRun
        row = self.db.get(QmrBacktestRun, run_id)
        if row is None: raise ValueError("QMR回测任务不存在。")
        return self.serialize_run(row)

    def list(self, **kwargs):
        rows, total = self.repository.list_runs(**kwargs)
        return [self.serialize_run(row) for row in rows], total

    def cancel(self, run_id):
        from app.database.models import QmrBacktestRun
        row = self.db.get(QmrBacktestRun, run_id)
        if row is None: raise ValueError("QMR回测任务不存在。")
        if row.status in ("SUCCESS", "FAILED", "CANCELLED"): return self.serialize_run(row)
        self.repository.request_cancel(row); return self.serialize_run(row)

    @staticmethod
    def serialize_run(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    @staticmethod
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
