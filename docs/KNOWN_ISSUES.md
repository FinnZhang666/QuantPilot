# Trade Companion v1.0.0-beta.1 Known Limitations

- The product is Paper Trading Only. Real broker orders and real position synchronization are intentionally unavailable.
- Strategy and closed-trade samples remain limited. Trade Plan count may be zero under current deterministic thresholds.
- Sharpe is not reported because the current sample and observation window are not reliable enough.
- Long-term Windows service stability and restart recovery still require Beta observation; no 30-day stability claim is made.
- Telegram Bot profile photos must be set manually through BotFather.
- Credentials exposed during development must be rotated before formal Beta operation. Values must remain only in local `.env`.
- OpenD is used for market data only. OpenD-dependent live tests require a separately running, logged-in local OpenD.
- SQLite supports the intended single-instance deployment. Multi-worker or clustered writes are unsupported.
- A full restore rehearsal is pending additional storage capacity; the active database must not be overwritten for testing.
- The E: drive is currently below the release storage threshold and must be expanded before large backups, VACUUM or rebuilds.
- `QuantPilot` remains only in internal package, database and repository compatibility identifiers during Beta.
- Starlette emits a TestClient cookie deprecation warning in five legacy tests; runtime behavior is unaffected.
