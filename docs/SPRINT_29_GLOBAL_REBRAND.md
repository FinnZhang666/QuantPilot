# Sprint 29: Global Rebrand Foundation

## Product identity

- Product: **Trade Companion**
- Chinese tagline: **陪你把每一笔交易做完**
- English tagline: **Your AI Trade Companion**

Trade Companion is an AI-assisted research and trade-lifecycle workspace. It
connects market data, feature calculation, strategy observations,
Opportunities, Reviews, and research evidence. It is a companion throughout the
research lifecycle, not a promise of profit or an instruction to trade.

## Scope

Sprint 29 changes user-visible branding only. It does not change strategies,
database schema, endpoint paths, request or response schemas, OpenD behavior,
scheduler behavior, Telegram commands, or trading safety boundaries.

For compatibility, these technical identifiers remain unchanged:

- GitHub repository and local directory: `QuantPilot`
- Python distribution: `quantpilot`
- Python application package: `app`
- SQLite default file: `data/quantpilot.db`
- Backup archive and internal compatibility identifiers
- Versioned AI prompt text and hash (preserved to avoid changing analysis behavior)

Repository, package, deployment image, domain, and CI/CD renaming should be
handled together in a future Repository Migration Sprint after Beta stability.

## User-visible surfaces

- Dashboard and login titles, brand header, logo alt text, and taglines
- FastAPI/OpenAPI title and product description
- Version Center product name and Sprint metadata
- CLI product headings and Telegram connection-test copy
- AI Review Analyst product identity
- README and current technical documentation references

No Dashboard layout was redesigned and no Telegram command or callback was
added, removed, or renamed.
