from datetime import datetime, timezone

from sqlalchemy import desc, func, select

from app.database.models import (
    BuyScoreRecord, QmrBacktestCase, QmrBacktestParameterSet, QmrBacktestRun,
    QmrCandidateRecord, QmrLiveSignal, QmrSignalPerformance, StrategyRecord,
    QmrExitEvaluation,
)
from app.qmr_live.tracking import QmrPerformanceTracker


QMR_CODE = "quality_mispricing_recovery"
QMR_NAME = "优质错杀修复"
QMR_SHORT_NAME = "QMR"
QMR_VERSION = "QMR-v1.0"
QMR_DESCRIPTION = (
    "在优质公司因市场恐慌、行业联动、短期事件或估值压缩出现异常大跌后，"
    "先判断公司与行业长期逻辑是否仍然成立，再等待卖压衰竭、资金回流和趋势修复，"
    "在反转早期产生介入信号。"
)


class StrategyCenterRepository:
    def __init__(self, db):
        self.db = db

    def get(self, code):
        return self.db.scalar(select(StrategyRecord).where(StrategyRecord.code == code))

    def list(self):
        return list(self.db.scalars(select(StrategyRecord).order_by(StrategyRecord.name)))

    def ensure_qmr(self):
        row = self.get(QMR_CODE)
        if row is None:
            row = StrategyRecord(code=QMR_CODE, name=QMR_NAME, version=QMR_VERSION,
                description=QMR_DESCRIPTION, is_enabled=True, config_json=self.default_config())
            self.db.add(row); self.db.commit()
        return row

    def set_enabled(self, row, enabled):
        row.is_enabled = bool(enabled)
        config = dict(row.config_json or {})
        config["operational_status"] = "ENABLED" if enabled else "DISABLED"
        row.config_json = config
        self.db.commit()
        return row

    def latest_backtest(self):
        return self.db.scalar(select(QmrBacktestRun).where(
            QmrBacktestRun.status == "SUCCESS").order_by(desc(QmrBacktestRun.id)).limit(1))

    def latest_candidates(self):
        latest = select(QmrCandidateRecord.symbol,
            func.max(QmrCandidateRecord.evaluation_time).label("at")).group_by(
            QmrCandidateRecord.symbol).subquery()
        return list(self.db.scalars(select(QmrCandidateRecord).join(latest,
            (QmrCandidateRecord.symbol == latest.c.symbol) &
            (QmrCandidateRecord.evaluation_time == latest.c.at)).order_by(
            desc(QmrCandidateRecord.combined_score))))

    def latest_buy_scores(self):
        latest = select(BuyScoreRecord.symbol,
            func.max(BuyScoreRecord.evaluation_time).label("at")).group_by(
            BuyScoreRecord.symbol).subquery()
        return list(self.db.scalars(select(BuyScoreRecord).join(latest,
            (BuyScoreRecord.symbol == latest.c.symbol) &
            (BuyScoreRecord.evaluation_time == latest.c.at)).order_by(
            desc(BuyScoreRecord.final_buy_score))))

    def live_signals(self):
        return list(self.db.scalars(select(QmrLiveSignal).order_by(
            desc(QmrLiveSignal.signal_time))))

    def cases(self, run_id=None):
        query = select(QmrBacktestCase)
        if run_id is not None:
            query = query.where(QmrBacktestCase.run_id == run_id)
        return list(self.db.scalars(query.order_by(desc(QmrBacktestCase.signal_time))))

    def parameter_sets(self):
        return list(self.db.scalars(select(QmrBacktestParameterSet).order_by(
            desc(QmrBacktestParameterSet.created_at))))

    def exit_evaluations(self, limit=100):
        return list(self.db.scalars(select(QmrExitEvaluation).order_by(
            desc(QmrExitEvaluation.evaluation_time)).limit(limit)))

    @staticmethod
    def default_config():
        return {"short_name": QMR_SHORT_NAME, "strategy_type": ["REVERSAL", "MEAN_REPAIR", "EVENT_REPAIR"],
                "market": "US", "universe": ["QQQ", "SPY"],
                "modules": ["Universe", "Quality", "Mispricing", "Recovery", "Buy Score",
                            "Backtest", "Live Signals", "Cases"],
                "operational_status": "RESEARCH"}


class StrategyCenterService:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.repository = StrategyCenterRepository(db)

    def ensure_qmr(self):
        return self.repository.ensure_qmr()

    def list(self):
        self.ensure_qmr()
        return [self.summary(row) for row in self.repository.list()]

    def get(self, code):
        row = self.repository.get(code)
        if row is None:
            raise KeyError("策略不存在。")
        if row.code != QMR_CODE:
            return self.summary(row)
        candidates = self.repository.latest_candidates()
        scores = self.repository.latest_buy_scores()
        signals = self.repository.live_signals()
        run = self.repository.latest_backtest()
        cases = self.repository.cases(run.id if run else None)
        return {**self.summary(row), "logic": ["QQQ + SPY 股票池", "公司质量筛选", "错杀识别",
            "止跌检测", "资金回流检测", "综合买入评分", "历史回测验证", "实时信号",
            "TG通知", "案例跟踪"],
            "current_candidates": [self._candidate(item, scores) for item in candidates],
            "current_signals": [self._signal(item) for item in signals],
            "backtest": self._backtest(run),
            "live_performance": QmrPerformanceTracker(self.db, self.settings).validation(),
            "exit_engine": {"current": [self._columns(item) for item in self.repository.exit_evaluations()],
                            "states": ["HOLD", "WATCH", "PROTECT", "REDUCE", "EXIT"]},
            "cases": self._case_summary(cases),
            "parameter_sets": [self._columns(item) for item in self.repository.parameter_sets()]}

    def set_enabled(self, code, enabled):
        row = self.repository.get(code)
        if row is None:
            raise KeyError("策略不存在。")
        self.repository.set_enabled(row, enabled)
        return self.summary(row)

    def summary(self, row):
        if row.code != QMR_CODE:
            return {"strategy_code": row.code, "strategy_name": row.name,
                    "strategy_version": row.version, "status": "ENABLED" if row.is_enabled else "DISABLED",
                    "description": row.description, "config": row.config_json}
        candidates = self.repository.latest_candidates()
        scores = self.repository.latest_buy_scores()
        signals = self.repository.live_signals()
        run = self.repository.latest_backtest()
        period = self._period(run, "5")
        status = self._status(row, run)
        latest_times = [item.evaluation_time for item in candidates] + [item.signal_time for item in signals]
        return {"strategy_id": row.id, "strategy_code": row.code, "strategy_name": row.name,
            "short_name": QMR_SHORT_NAME, "strategy_version": row.version, "status": status,
            "is_enabled": row.is_enabled, "description": row.description,
            "strategy_type": (row.config_json or {}).get("strategy_type", []),
            "market": "US", "universe": "QQQ + SPY",
            "current_candidate_count": sum(item.candidate_status == "WATCH" for item in candidates),
            "current_entry_signal_count": sum(item.buy_status in {
                "EARLY_ENTRY", "CONFIRMED_ENTRY", "STRONG_ENTRY"} for item in scores),
            "historical_sample_count": None if run is None else (run.summary_json or {}).get("sample_count", 0),
            "historical_win_rate_5d": period.get("positive_rate") if period else None,
            "last_signal_at": signals[0].signal_time if signals else None,
            "last_run_at": max(latest_times) if latest_times else None,
            "latest_backtest_id": run.id if run else None,
            "signal_total": len(signals), "opportunity_count": 0,
            "average_score": round(sum(item.final_buy_score for item in scores) / len(scores), 2) if scores else 0,
            "signal_counts": self._counts(signals, "signal_level"), "failed_gates": {},
            "supported_timeframes": ["1d", "30m"], "symbol_templates": ["QQQ", "SPY"],
            "score_distribution": self._score_distribution(scores)}

    @staticmethod
    def _status(row, run):
        if not row.is_enabled: return "DISABLED"
        if run and run.strategy_status == "REJECTED": return "REJECTED"
        if run and run.strategy_status == "VALIDATED": return "ENABLED"
        return "RESEARCH"

    @staticmethod
    def _period(run, key):
        if not run: return {}
        periods = (run.summary_json or {}).get("holding_periods") or {}
        return periods.get(key) or periods.get(key + "d") or periods.get(int(key)) or {}

    def _backtest(self, run):
        if not run: return None
        summary = run.summary_json or {}
        return {"id": run.id, "range": [run.data_start, run.data_end], "status": run.strategy_status,
                "sample_count": summary.get("sample_count"), "holding_periods": summary.get("holding_periods", {}),
                "best_holding_period": summary.get("best_holding_period"),
                "best_target_stop": summary.get("best_target_stop"),
                "max_drawdown": summary.get("max_drawdown"), "warnings": run.warnings_json}

    @staticmethod
    def _candidate(item, scores):
        score = next((value for value in scores if value.symbol == item.symbol), None)
        return {"symbol": item.symbol, "quality_score": item.quality_score,
                "mispricing_score": item.mispricing_score,
                "recovery_score": None if score is None else score.recovery_score,
                "buy_score": None if score is None else score.final_buy_score,
                "status": item.candidate_status if score is None else score.buy_status}

    @staticmethod
    def _signal(item):
        performance = (float(item.latest_price) / float(item.signal_price) - 1) * 100 \
            if item.latest_price is not None and item.signal_price else None
        return {"signal_id": item.signal_id, "symbol": item.symbol, "signal_time": item.signal_time,
                "signal_price": item.signal_price, "buy_score": item.buy_score,
                "signal_level": item.signal_level, "current_return": performance,
                "status": item.status}

    @staticmethod
    def _case_summary(cases):
        labels = {"SUCCESS": 0, "FAILED": 0, "FALSE_RECOVERY": 0,
                  "MAJOR_WINNER": 0, "OUTLIER_WINNER": 0}
        for item in cases:
            if item.result in labels: labels[item.result] += 1
            returns = item.mfe_json or {}
            mfe = max([float(value) for value in returns.values() if value is not None] or [0])
            mae = min([float(value) for value in (item.mae_json or {}).values() if value is not None] or [0])
            if mfe >= 50: labels["OUTLIER_WINNER"] += 1
            elif mfe >= 20: labels["MAJOR_WINNER"] += 1
            if mae <= -10: labels["FALSE_RECOVERY"] += 1
        return {"counts": labels, "items": [StrategyCenterService._columns(item) for item in cases[:100]]}

    @staticmethod
    def _counts(rows, field):
        result = {}
        for row in rows:
            value = getattr(row, field); result[value] = result.get(value, 0) + 1
        return result

    @staticmethod
    def _score_distribution(rows):
        values = [item.final_buy_score for item in rows]
        return {"0-39": sum(v < 40 for v in values), "40-59": sum(40 <= v < 60 for v in values),
                "60-79": sum(60 <= v < 80 for v in values), "80-100": sum(v >= 80 for v in values)}

    @staticmethod
    def _columns(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
