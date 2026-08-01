"""Read-only validation for the Windows Phase 3 data foundation."""

import argparse
import json
import sqlite3
import time
from pathlib import Path


def scalar(connection, sql, parameters=()):
    return connection.execute(sql, parameters).fetchone()[0]


def duplicate_count(connection, table, columns):
    grouped = ", ".join(columns)
    sql = (
        "SELECT COALESCE(SUM(c - 1), 0) FROM ("
        f"SELECT COUNT(*) AS c FROM {table} GROUP BY {grouped} HAVING COUNT(*) > 1"
        ")"
    )
    return scalar(connection, sql)


def feature_unique_index(connection):
    expected = {
        "symbol", "interval", "timestamp_utc", "feature_name",
        "feature_version", "parameters_hash", "data_source",
    }
    for row in connection.execute("PRAGMA index_list(feature_values)"):
        if not row[2]:
            continue
        columns = {
            item[2] for item in connection.execute(f"PRAGMA index_info('{row[1]}')")
        }
        if columns == expected:
            return row[1]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--integrity", action="store_true")
    parser.add_argument("--quick-check", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    connection = sqlite3.connect(f"file:{args.database.as_posix()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    try:
        bars = [
            {
                "symbol": row[0], "interval": row[1], "earliest": row[2],
                "latest": row[3], "total": row[4],
            }
            for row in connection.execute(
                "SELECT symbol, interval, MIN(timestamp_utc), MAX(timestamp_utc), COUNT(*) "
                "FROM market_bars GROUP BY symbol, interval ORDER BY symbol, interval"
            )
        ]
        unique_feature_index = feature_unique_index(connection)
        result = {
            "database": str(args.database.resolve()),
            "database_bytes": args.database.stat().st_size,
            "alembic_revision": scalar(connection, "SELECT version_num FROM alembic_version"),
            "covered_symbols": scalar(connection, "SELECT COUNT(DISTINCT symbol) FROM market_bars"),
            "total_bars": scalar(connection, "SELECT COUNT(*) FROM market_bars"),
            "total_features": scalar(connection, "SELECT COALESCE(MAX(id), 0) FROM feature_values"),
            "feature_rows_inserted_by_jobs": scalar(
                connection,
                "SELECT COALESCE(SUM(inserted_rows), 0) FROM feature_calculation_jobs "
                "WHERE status = 'SUCCESS'",
            ),
            "active_candidates": scalar(
                connection,
                "SELECT COUNT(*) FROM candidate_pool_entries WHERE status != 'EXPIRED'",
            ),
            "trade_plans": scalar(connection, "SELECT COUNT(*) FROM trade_plans"),
            "duplicate_bars": duplicate_count(
                connection, "market_bars", ["instrument_id", "interval", "timestamp_utc"]
            ),
            "duplicate_features": 0 if unique_feature_index else None,
            "feature_unique_index": unique_feature_index,
            "duplicate_candidates": duplicate_count(
                connection, "candidate_pool_entries", ["symbol", "market", "pool_date"]
            ),
            "bars_by_symbol_interval": bars,
            "feature_jobs": [list(row) for row in connection.execute(
                "SELECT status, COUNT(*), COALESCE(SUM(output_rows), 0), "
                "COALESCE(SUM(failed_features), 0) FROM feature_calculation_jobs "
                "GROUP BY status ORDER BY status"
            )],
            "strategy_runs": [list(row) for row in connection.execute(
                "SELECT run_id, status, bars_evaluated, signals_written, errors_count "
                "FROM strategy_runs ORDER BY id DESC LIMIT 5"
            )],
            "signals": [list(row) for row in connection.execute(
                "SELECT signal_type, status, COUNT(*) FROM candidate_signals "
                "GROUP BY signal_type, status ORDER BY signal_type, status"
            )],
            "candidate_pool": [list(row) for row in connection.execute(
                "SELECT symbol, direction, final_score, rank, status "
                "FROM candidate_pool_entries ORDER BY pool_date DESC, rank LIMIT 20"
            )],
        }
        if args.integrity:
            result["integrity_check"] = scalar(connection, "PRAGMA integrity_check")
        if args.quick_check:
            result["quick_check"] = scalar(connection, "PRAGMA quick_check")
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
