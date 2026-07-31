# Sprint 41 — Dashboard UX Refresh

## Design goals

Sprint 41 Part B productizes the existing local Dashboard without changing trading logic, API contracts, database schema, OpenD, or Telegram Runtime. The interface is dark, compact, information-dense, and suitable for a release demonstration. Trade Companion remains a research and trade-lifecycle workspace rather than a broker terminal.

## Visual system

- Dark neutral surfaces with restrained blue and teal accents.
- Green, amber, red, and neutral status treatments always include text labels.
- Shared 11px-radius cards, compact spacing, visible borders, and limited shadow.
- One shared button, table, badge, empty-state, filter, and focus system.
- The approved logo is reused unchanged. The PNG filename remains an internal compatibility name.

## Layout system

The shell uses a fixed grouped sidebar, a compact status header, a responsive content area, and a version footer. The content width supports dense layouts up to 1680px. At 1280px KPI grids reduce to three columns; at 900px the sidebar becomes a drawer; at 600px cards and forms use one column.

## Navigation

Navigation is grouped into Workspace, Market Intelligence, Trade Planning, Portfolio, Research & Review, AI Companion, Operations, and More. Every existing Dashboard route remains available. The sidebar can collapse to icons with browser-native tooltips and persists that choice in local storage. Small screens use a dismissible drawer.

## Language strategy

The default locale is `zh-CN`. A centralized dictionary in `app/dashboard/static/ui.js` provides `zh-CN` and `en-US` labels for the shell, navigation, page titles, common actions, empty states, and status labels. The selected language is kept in local storage. Product names, symbols, provider names, and domain enum codes may remain in English.

## Card system

Shared classes provide KPI, data, status, chart-ready, and empty cards. The Dashboard home uses six compact KPI cards, a three-panel market/opportunity/portfolio row, and a lower trade-plan/research row. Data continues to come from existing read services and APIs.

## Table system

Tables share compact rows, sticky headers, hover feedback, right-aligned numeric cells, consistent empty values, overflow handling, and responsive containers. Existing filters and pagination contracts are preserved.

## Button system

The shared button variants are primary, secondary, ghost, success, danger, and disabled. Focus, hover, active, and disabled states are explicit. Disabled controls cannot receive pointer actions.

### Button function audit

- Refresh, filter, search, pagination, details, related-object navigation, Runtime controls, and Telegram Preview retain real routes or event handlers.
- The Telegram template selector is visibly disabled because this release exposes only Symbol Overview preview.
- No `href="#"` placeholder remains in the shell.
- Preview actions without related objects render as disabled controls with explanatory titles.
- No Telegram send action is present.

## Empty states

Trade Plans, position plans, Trade Reviews, AI Companion, Market Snapshot, and home sections use contextual titles and explanations rather than a bare “no data” cell. Actions are shown only when a real route or operation exists.

## Header and footer

The header shows Eastern Time and compact system/OpenD/AI/Telegram badges populated from the existing Dashboard summary. It never initiates an OpenD or Telegram action. The footer loads product version, Sprint, and Alembic revision from `/api/platform/version`.

## Version source

`app/version.py` is the single source for Product, Version, and Sprint. FastAPI/OpenAPI imports `PRODUCT` and `VERSION`; Version Center and the global footer read the platform version endpoint. The release values remain:

- Product: Trade Companion
- Version: `1.0.0-rc2`
- Sprint: `40`
- Alembic: `0019`

## Login

The login page reuses the approved logo, removes internal implementation copy, provides a properly labelled Token field, an accessible show/hide control, focused error presentation, and the product safety boundary.

## Telegram Preview

Telegram Preview uses a compact settings panel and a Telegram-style message container. It preserves `Preview Mode` and `Sent: NO`, does not read a Bot token, and does not send messages. Missing Trade Plan, Holding, Review, or AI objects stay visibly unavailable.

## Accessibility

Controls have labels or `aria-label`, keyboard focus rings, visible disabled states, text-backed status colors, predictable source order, and accessible navigation naming. This is a practical baseline rather than a formal WCAG certification.

## Screenshots

Release-review screenshots are generated from a freshly started process using the current commit and stored outside the repository in `/tmp/trade_companion_sprint41_ui_refresh/`. This avoids committing environment-specific images.

## Known limitations

- The project still uses lightweight server-rendered HTML plus vanilla JavaScript; it does not include a frontend build pipeline.
- Domain payloads may contain stable English enums, symbols, strategy names, and provider names by design.
- Empty local Trade Plan, Holding, Review, or AI tables are displayed honestly; no demo records are fabricated.
- Telegram Preview is presentation-only. Windows deployment, real Telegram Runtime, and OpenD runtime validation remain outside this Sprint.
