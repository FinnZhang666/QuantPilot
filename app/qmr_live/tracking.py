from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import yaml
from sqlalchemy import select

from app.database.models import QmrSignalParticipation, QmrSignalPerformance
from app.qmr_live.repository import QmrLiveRepository


class QmrPerformanceTracker:
    """Track persisted QMR signals using closed daily bars only."""

    def __init__(self, db, settings):
        self.db = db
        self.repository = QmrLiveRepository(db)
        self.config = yaml.safe_load(
            Path(settings.qmr_live_config_file).read_text(encoding="utf-8")
        )

    def run(self, evaluation_time=None, signal_id=None):
        at = self._utc(evaluation_time or datetime.now(timezone.utc))
        signals = ([self.repository.signal(signal_id)] if signal_id else
                   self.repository.signals())
        result = {"scanned": 0, "updated": 0, "completed": 0, "failed": 0}
        for signal in [item for item in signals if item is not None]:
            result["scanned"] += 1
            try:
                bars = self.repository.bars(signal, at)
                if bars:
                    signal.latest_price = bars[-1].close
                for window in self.config["tracking_windows_days"]:
                    row = self._track_window(signal, bars, int(window), at)
                    result["updated"] += 1
                    result["completed"] += int(row.completed)
                if len(bars) >= max(self.config["tracking_windows_days"]):
                    final = self._performance(signal.signal_id,
                                              max(self.config["tracking_windows_days"]))
                    signal.status = "SUCCESS" if float(final.return_pct or 0) > 0 else "FAILED"
                    signal.completed_at = at
                self.db.commit()
            except Exception:
                self.db.rollback()
                result["failed"] += 1
        return result

    def _track_window(self, signal, bars, window, at):
        row = self._performance(signal.signal_id, window)
        if row is None:
            row = QmrSignalPerformance(signal_id=signal.signal_id, window_days=window,
                                       completed=False, evaluated_at=at)
            self.db.add(row)
        selected = bars[:window]
        row.evaluated_at = at
        if selected:
            entry = float(signal.signal_price)
            closes = [float(item.close) for item in selected]
            highs = [float(item.high) for item in selected]
            lows = [float(item.low) for item in selected]
            row.last_price, row.max_price, row.min_price = closes[-1], max(highs), min(lows)
            row.return_pct = (closes[-1] / entry - 1) * 100
            row.mfe_pct = (max(highs) / entry - 1) * 100
            row.mae_pct = (min(lows) / entry - 1) * 100
            row.completed = len(selected) >= window
            row.case_label = self._case_label(float(row.mfe_pct), float(row.mae_pct))
        return row

    def statistics(self, window_days=5, rolling=None):
        query = select(QmrSignalPerformance).where(
            QmrSignalPerformance.window_days == window_days,
            QmrSignalPerformance.completed.is_(True),
        ).order_by(QmrSignalPerformance.evaluated_at.desc())
        rows = list(self.db.scalars(query))
        if rolling:
            rows = rows[:int(rolling)]
        returns = [float(row.return_pct) for row in rows if row.return_pct is not None]
        gains = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        return {"window_days": window_days, "rolling": rolling or "ALL",
                "sample_count": len(returns),
                "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
                "average_return": mean(returns) if returns else None,
                "median_return": median(returns) if returns else None,
                "average_mfe": self._average(rows, "mfe_pct"),
                "average_mae": self._average(rows, "mae_pct"),
                "profit_factor": (sum(gains) / abs(sum(losses))) if losses else None}

    def validation(self):
        live = self.statistics(5)
        recent = self.statistics(5, self.config["drift"]["window"])
        run = self.repository.latest_strategy_run()
        historical = None
        if run and run.summary_json:
            historical = ((run.summary_json.get("holding_periods") or {}).get("5") or
                          (run.summary_json.get("holding_periods") or {}).get("5d") or {}).get("positive_rate")
        delta = None if historical is None or live["win_rate"] is None else live["win_rate"] - historical
        drift = bool(historical is not None and recent["sample_count"] >= 20 and
                     recent["win_rate"] is not None and
                     historical - recent["win_rate"] >= self.config["drift"]["win_rate_drop_threshold"])
        return {"historical_win_rate_5d": historical, "live_win_rate_5d": live["win_rate"],
                "live_vs_backtest_delta": delta,
                "strategy_drift": "STRATEGY_DRIFT" if drift else "STABLE",
                "rolling": {str(size): self.statistics(5, size) for size in (20, 50, 100)},
                "all": live}

    def user_statistics(self, telegram_user_id):
        rows = list(self.db.scalars(select(QmrSignalParticipation).where(
            QmrSignalParticipation.telegram_user_id == telegram_user_id)))
        values = []
        for participation in rows:
            performance = self._performance(participation.signal_id, 20)
            if performance and performance.completed and performance.return_pct is not None:
                values.append((participation.symbol, float(performance.return_pct)))
        best = max(values, key=lambda item: item[1]) if values else None
        worst = min(values, key=lambda item: item[1]) if values else None
        return {"follow_count": len(rows), "completed": len(values),
                "wins": sum(value > 0 for _, value in values),
                "losses": sum(value < 0 for _, value in values),
                "win_rate": sum(value > 0 for _, value in values) / len(values) if values else None,
                "average_return": mean(value for _, value in values) if values else None,
                "best": best, "worst": worst}

    def _performance(self, signal_id, window):
        return self.db.scalar(select(QmrSignalPerformance).where(
            QmrSignalPerformance.signal_id == signal_id,
            QmrSignalPerformance.window_days == window))

    def _case_label(self, mfe, mae):
        labels = self.config["case_labels"]
        if mfe >= labels["outlier_winner_mfe_pct"]:
            return "OUTLIER_WINNER"
        if mfe >= labels["major_winner_mfe_pct"]:
            return "MAJOR_WINNER"
        if mae <= labels["false_recovery_mae_pct"]:
            return "FALSE_RECOVERY"
        return None

    @staticmethod
    def _average(rows, field):
        values = [float(getattr(row, field)) for row in rows if getattr(row, field) is not None]
        return mean(values) if values else None

    @staticmethod
    def _utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
