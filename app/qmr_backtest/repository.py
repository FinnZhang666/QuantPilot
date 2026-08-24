from datetime import timedelta, timezone

from sqlalchemy import desc, func, select

from app.database.models import (
    BuyScoreRecord, MarketBar, QmrBacktestCase, QmrBacktestParameterSet,
    QmrBacktestResult, QmrBacktestRun, QmrWalkForwardResult, RecoveryScoreRecord, UniverseInstrument,
    UniverseMembership,
)


class QmrBacktestRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    def parameter_set(self, name, version, config_hash, parameters):
        row = self.db.scalar(select(QmrBacktestParameterSet).where(
            QmrBacktestParameterSet.name == name,
            QmrBacktestParameterSet.strategy_version == version,
        ))
        if row is None:
            row = QmrBacktestParameterSet(name=name, strategy_version=version,
                configuration_hash=config_hash, parameters_json=parameters)
            self.db.add(row); self.db.commit()
        elif row.configuration_hash != config_hash:
            raise ValueError("同名参数集已存在且内容不同，请使用新参数集名称。")
        return row

    def create_run(self, parameter_set, run_key, start, end, model_version, symbols, estimated):
        row = QmrBacktestRun(parameter_set_id=parameter_set.id, run_key=run_key,
            model_version=model_version, strategy_version=parameter_set.strategy_version,
            universe_version="POINT_IN_TIME_MEMBERSHIP_UNAVAILABLE", data_start=start, data_end=end,
            symbols_json=symbols or [], status="PENDING", strategy_status="RESEARCH",
            coverage_json={}, warnings_json=[], summary_json={}, estimated_storage_bytes=estimated)
        self.db.add(row); self.db.commit()
        return row

    def signals(self, start, end, model_version, symbols=None):
        query = select(BuyScoreRecord, UniverseInstrument, RecoveryScoreRecord).join(
            UniverseInstrument, UniverseInstrument.symbol == BuyScoreRecord.symbol,
        ).join(RecoveryScoreRecord, RecoveryScoreRecord.id == BuyScoreRecord.recovery_score_id).where(
                BuyScoreRecord.evaluation_time >= start, BuyScoreRecord.evaluation_time <= end,
                BuyScoreRecord.model_version == model_version)
        if symbols:
            query = query.where(BuyScoreRecord.symbol.in_(symbols))
        output = []
        for score, instrument, recovery in self.db.execute(query.order_by(
                BuyScoreRecord.symbol, BuyScoreRecord.evaluation_time)):
            score._qmr_backtest_market_state = recovery.market_state
            score._qmr_backtest_recovery_snapshot = recovery.score_components_json
            output.append((score, instrument))
        return output

    def bars(self, symbol, start, end, interval="1d"):
        names = (symbol.upper(), "US." + symbol.upper().replace("US.", ""))
        return list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol.in_(names), MarketBar.interval == interval,
            MarketBar.timestamp_utc >= start, MarketBar.timestamp_utc <= end,
            MarketBar.is_blank.is_(False),
        ).order_by(MarketBar.timestamp_utc)))

    def case_exists(self, run_id, buy_score_id, level):
        return self.db.scalar(select(QmrBacktestCase.id).where(
            QmrBacktestCase.run_id == run_id, QmrBacktestCase.buy_score_id == buy_score_id,
            QmrBacktestCase.entry_level == level,
        )) is not None

    def save_case(self, values):
        row = QmrBacktestCase(**values); self.db.add(row); self.db.flush(); return row

    def save_result(self, values):
        self.db.add(QmrBacktestResult(**values))

    def save_fold(self, values):
        self.db.add(QmrWalkForwardResult(**values))

    def cases(self, run_id):
        return list(self.db.scalars(select(QmrBacktestCase).where(
            QmrBacktestCase.run_id == run_id).order_by(QmrBacktestCase.signal_time)))

    def list_runs(self, limit=100, offset=0, status=None):
        query = select(QmrBacktestRun)
        if status: query = query.where(QmrBacktestRun.status == status.upper())
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = list(self.db.scalars(query.order_by(desc(QmrBacktestRun.id)).offset(offset).limit(limit)))
        return rows, total

    def historical_universe_coverage(self, start, end):
        """Current membership schema has no effective_from/to history; never claim PIT coverage."""
        memberships = self.db.scalar(select(func.count()).select_from(UniverseMembership)) or 0
        return {"status": "UNAVAILABLE", "membership_rows": memberships,
                "requested_start": start.isoformat(), "requested_end": end.isoformat(),
                "warning": "历史QQQ/SPY成分有效期不可用，存在幸存者偏差。"}

    def data_coverage(self, signals):
        if not signals:
            return {"signal_start": None, "signal_end": None, "symbols": 0}
        times = [self.aware(row[0].evaluation_time) for row in signals]
        return {"signal_start": min(times).isoformat(), "signal_end": max(times).isoformat(),
                "symbols": len({row[0].symbol for row in signals})}

    def mark_running(self, run, now):
        run.status, run.started_at, run.progress_pct = "RUNNING", now, 0
        self.db.commit()

    def finish(self, run, status, strategy_status, summary, coverage, warnings, now, error=None):
        run.status, run.strategy_status, run.summary_json = status, strategy_status, summary
        run.coverage_json, run.warnings_json = coverage, warnings
        run.progress_pct, run.completed_at, run.error_summary = 100, now, error
        self.db.commit()

    def update_progress(self, run, progress):
        run.progress_pct = progress; self.db.commit()

    def request_cancel(self, run):
        run.cancel_requested = True; self.db.commit()

    def latest_run(self):
        return self.db.scalar(select(QmrBacktestRun).order_by(desc(QmrBacktestRun.id)).limit(1))
