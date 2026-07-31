# Trade Companion 1.0.0-rc2 Known Issues

- Windows production deployment has not been validated in this RC.
- Telegram Product Layer supports ViewModel, formatter, buttons, deep links and preview, but is not connected to
  the Windows Bot Runtime; Preview does not send messages.
- External AI Companion Provider has not been production-validated; offline Mock/dry-run is the tested baseline.
- Broker execution and real-money order submission are intentionally unavailable.
- OpenD-dependent history/realtime tests require a separately running, logged-in local OpenD and are not part of
  the offline regression baseline.
- SQLite supports the intended single-instance deployment. Multi-worker or clustered writes are unsupported.
- No verified local backup was present during the RC2 audit; create and verify one before deployment.
- Dashboard authentication is a local administrator token, not a full multi-user identity system.
- `QuantPilot` repository/package/database compatibility names remain until the dedicated migration release.
- Starlette currently emits a TestClient per-request cookie deprecation warning in five legacy tests; runtime
  behavior and test outcomes are unaffected.
