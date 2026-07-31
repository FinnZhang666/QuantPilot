# Dashboard API Permission Matrix

`DASHBOARD_READONLY_PUBLIC` changes read access only. It never authorizes a
write operation. `require_read` permits an anonymous request only when the
flag is `true`; otherwise the dashboard administrator token is required.

## A. Public ReadOnly

The following Dashboard API families use `require_read`. They are anonymous
GET endpoints only when `DASHBOARD_READONLY_PUBLIC=true`:

| API family | Methods used by Dashboard | Data purpose |
| --- | --- | --- |
| `/api/dashboard/*` | GET | Summary, strategy summary, data quality |
| `/api/platform/health` | GET | Cross-platform health |
| `/api/platform/runtime` | GET | Runtime diagnostics |
| `/api/platform/version` | GET | Product and schema version |
| `/api/runtime/status` | GET | Runtime state |
| `/api/market-regime/current`, `/history` | GET | Market regime |
| `/api/candidate-pool*` | GET | Candidate pool and run history |
| `/api/opportunities*` | GET | Opportunity list and detail |
| `/api/trade-plans*` | GET | Trade plan list, detail and history |
| `/api/user-positions*` | GET | Position list, detail and statistics |
| `/api/reviews*` | GET | Trade Review list, detail and statistics |
| `/api/review*` | GET | Legacy opportunity-review read model |
| `/api/ai-review*` | GET | AI Review list, detail and statistics |
| `/api/companion-analyses*` | GET | Companion analysis history |
| `/api/market-snapshots*` | GET | Market Snapshot list and detail |
| `/api/watchlists/*/snapshots` | GET | Portfolio watchlist snapshots |
| `/api/portfolios*`, `/api/holdings*` | GET | Portfolio read model |
| `/api/research*` | GET | Research workspaces and read-only evidence |
| `/api/development/issues*` | GET | Product feedback and issue views |
| `/api/symbols/*` | GET | Symbol overview |
| `/api/telegram-preview` | GET | Rendered Telegram preview data |

Public GET handlers must not synchronize, generate, repair or otherwise write
data. In particular, `GET /api/research` no longer calls `sync_all()`.

## B. Authenticated

The current application has no separate non-admin Dashboard session. When
`DASHBOARD_READONLY_PUBLIC=false`, every Class A endpoint becomes authenticated
and uses the dashboard administrator token. This preserves the existing local
deployment contract without introducing a new user system in Phase 2.

## C. Admin Only

These operations always require the dashboard administrator token, regardless
of the Public ReadOnly flag:

| API family | Methods | Reason |
| --- | --- | --- |
| `/api/platform/config` | GET | Safe configuration still exposes operational metadata |
| `/api/platform/backups` | GET, POST | Backup inventory and creation |
| `/api/runtime/start`, `/stop` | POST | Runtime mutation |
| `/api/candidate-pool/build`, `/refresh`, `/*/expire` | POST | Candidate mutation |
| `/api/market-regime/evaluate` | POST | Evaluation write |
| `/api/review/run` | POST | Review generation |
| `/api/ai-review/run`, `/*/retry` | POST | AI job mutation |
| `/api/development/issues*` | POST, PATCH | Issue mutation |
| `/api/research/*` | POST, PATCH | Notes, attachments and investigation mutation |
| `/internal/*` | All | Internal generation and portfolio mutation |
| Feature, history, strategy and realtime control endpoints | POST, PATCH, DELETE | Runtime or database mutation |

An anonymous request to a Class C endpoint must return HTTP 401. Public
ReadOnly mode must not reduce the OpenAPI path set or remove admin operations.
