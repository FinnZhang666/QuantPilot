# Real Data Validation

This layer closes the data-readiness gaps for QMR without changing its strategy,
recovery, execution, OpenD, or paper-trading behavior.

## Universe reliability

The configured universes are QQQ, SPY, SOXX, SMH, IGV, and IWM. Each fund has
an ordered primary/fallback provider list. A fetched payload must parse to a
non-empty member set before it can replace active membership. If all remote
providers fail, the service reads the persistent last-known-good (LKG) payload,
marks the run degraded/stale, and does **not** synchronize removals. An empty or
failed download can therefore never inactivate the existing universe.

`universe_update_runs.summary_json` contains the primary/fallback/actual source,
member and change counts, fetch/effective timestamps, quality, fallback/cache
flags, and failure reason. The cache stores only previously validated payloads.

## Point-in-time fundamentals

`FundamentalsProvider` exposes `get_latest` and `get_as_of`. The database adapter
selects only snapshots whose `available_at` is at or before the evaluation time.
Provider-specific valuation fields and peer samples remain in the existing
snapshot payload, so QMR is vendor-independent and no fabricated data is needed.

Quality factors missing from a snapshot are excluded from the denominator. The
available factors are reweighted to 100, while coverage and confidence remain
explicit. Mispricing uses the same principle and follows this comparison order:

1. explicit peers
2. industry peers
3. sector peers
4. market benchmark
5. historical self

Small samples lower peer confidence. Value-trap flags are deductions only; they
do not replace Buy Score. Leveraged instruments use the existing
`instrument_mappings` underlying for fundamentals and valuation.

## Money-flow capability and degradation

The capability object records market, asset type, provider, supported sessions,
historical/realtime support, supported fields, and reason. Provider results use:

`AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, `UNSUPPORTED`, `STALE`, or
`PERMISSION_DENIED`.

Unavailable values are never represented as zero. A money-flow regime is
`UNKNOWN` unless the input is available and meets the configured coverage
threshold. Recovery and Exit continue with available factors and normalized
weights; confidence falls when money flow is absent.

## Freshness and QMR explainability

`DataQuality` is the common shape for availability, status, freshness, coverage,
source, confidence, timestamp, and safe errors. TTLs differ for universe,
fundamentals, daily/intraday bars, money flow, market context, and sector context.

QMR responses retain all old fields and add `data_quality`, `coverage`,
`confidence`, `reason_codes`, `missing_factors`, `source_timestamp`, and
`money_flow_status`. Common reason codes include:

- `UNIVERSE_DATA_INCOMPLETE`
- `FUNDAMENTALS_INSUFFICIENT`
- `QUALITY_BELOW_THRESHOLD`
- `MISPRICING_NOT_EXTREME`
- `RECOVERY_NOT_READY` (owned by the downstream Recovery stage)
- `DATA_STALE`

The QMR research detail page displays coverage, source timestamps, peer method,
missing factors, and reason codes. These are explanations, not new signals.

## Windows validation handoff

On the next Windows runtime session:

1. Run Universe dry/update checks and confirm all six funds use primary,
   fallback, or LKG without membership loss.
2. Verify real fundamentals snapshots include correct publication timestamps.
3. Query money-flow capability/status for APP, MU, and SOXL and retain provider
   permission/data-insufficient outcomes exactly as returned.
4. Run QMR dry-run and inspect reason-code distribution before enabling writes.
5. Confirm OpenD, Telegram, and paper/real isolation behavior is unchanged.
