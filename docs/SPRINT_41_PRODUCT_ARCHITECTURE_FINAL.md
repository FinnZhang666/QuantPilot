# Sprint 41 Part C — Product Architecture Finalization

## Dashboard information architecture

Trade Companion now organizes its internal product workspace around user workflows rather than database entities:

1. **工作台 / Workspace**
2. **市场 / Market**
3. **策略 / Strategy**
4. **AI**
5. **产品运营 / Product Operations**
6. **Strategy Lab**
7. **更多 / More**

Existing object routes remain compatible, but `Opportunities` and `User Positions` are intentionally absent from the primary navigation. Candidate Pool is the unified opportunity entry. User Positions remain available as a supporting participation record rather than a primary product surface.

## Navigation

| Area | Primary pages |
|---|---|
| Market | Market Regime, Market Monitor, Candidate Pool |
| Strategy | Trade Plans, Paper Positions, Trade Reviews, Strategy Scoreboard |
| AI | AI Trade Interpretation, AI Strategy Review, Telegram Preview |
| Product Operations | User Feedback, User Behavior, Bot Statistics, User Intelligence |
| Strategy Lab | Strategy Experiments, Parameter Comparison, Research Center |
| More | Version Center, System Monitor, Runtime Logs |

The sidebar uses the shared Sprint 41 responsive and collapsed behavior. No duplicate business route or API was introduced.

## Market module

### Market Regime

Market Regime continues to show the existing trend, risk, volatility, and LONG/SHORT bias facts. It remains the page that answers whether the current environment is suitable for strategy activity; the Dashboard does not recompute those values.

### Market Monitor

Market Monitor is a presentation view over existing Market Snapshot data, not a market-wide scanner. The administrator investment watchlist appears first with Symbol, Candidate, Trade Plan, Holding, Review/AI availability, and update time. Review and AI cells remain unavailable when existing read models do not expose reliable links.

User Watchlist Summary is deliberately empty until a reliable multi-user aggregation source exists. The page never expands or fabricates user identities or counts.

## Strategy module

- **Trade Plans** keeps the current system plan view.
- **Paper Positions** is clearly defined as a future standardized simulation based on Trade Plans, not a customer position. No paper position, order, or trade is created in this Sprint.
- **Trade Reviews** keeps objective completed-trade review data.
- **Strategy Scoreboard** presents existing strategy names, versions, signal count, and latest activity. Win rate, average return, Profit Factor, and average holding remain `—` until a reliable common statistic exists.

## Product Operations

### Feedback Center

Feedback Center reuses existing `DevelopmentIssue` records with `source_type=USER_FEEDBACK`. It provides local search and status filtering without changing the API schema or database. Product-facing status interpretation is:

- `INBOX` → Open
- `INVESTIGATING` → In Progress
- `COMPLETED` → Released
- `REJECTED` → Rejected

The existing `evidence_json.admin_note`, when present, is displayed as an administrator note. Creation through Telegram and dedicated note editing remain disabled until the corresponding runtime is formally implemented.

### User Behavior, Bot Statistics, User Intelligence

These pages establish the final information architecture and metric definitions. They intentionally show a professional unavailable state because the current database has no unified behavior event source. No DAU, WAU, follow rate, click rate, delivery rate, or user ranking is inferred from unrelated tables.

## Telegram feedback flow

The Telegram product layer now exposes presentation-only action models:

```text
💡 更多
  └─ 提交建议
      ├─ 🐞 Bug
      ├─ 💡 功能建议
      ├─ 📈 新策略
      ├─ 🌍 新市场
      └─ ⭐ 其它
```

AI analysis presentation also defines `👍 有帮助` and `👎 没帮助` actions. These are deterministic callback-data models only. They do not register commands, start Polling/Webhook, write feedback, or send Telegram messages.

Planned administrator notification policy:

- Bug, high-priority feedback, and repeated suggestions may notify administrators.
- Ordinary feedback only enters Feedback Center.
- This Sprint implements no notification runtime.

## Strategy Lab

Strategy Lab is an internal research area. Strategy Experiments reuses the existing strategy observation view; Parameter Comparison is an explicit non-operational placeholder; Research Center retains the evidence workspace. No parameter optimization or strategy mutation is performed.

## Version Center and system operations

Version Center now only displays Product, Version, Sprint, Build, Git Commit, Migration, branch, and release notes. Operational health moved to System Monitor. Runtime Logs only presents persisted error summaries and never reads or exposes local log files directly.

## Future roadmap

Future releases may connect feedback to Telegram Runtime, add a dedicated behavior event source, calculate user-level product analytics, associate released roadmap items with feedback, and implement audited paper positions. Each requires its own database/API/runtime Sprint and is not implied by the current presentation pages.

## Boundaries

- No database or Alembic migration.
- No API schema change.
- No strategy, feature, candidate, Trade Plan, Review, or AI Runtime change.
- No OpenD or Telegram Runtime change.
- No message send and no order execution.
