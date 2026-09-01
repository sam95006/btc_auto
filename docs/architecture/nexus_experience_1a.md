# NEXUS-EXPERIENCE-1A — Product Architecture & Data Foundation

Foundation for the NEXUS product-experience program. Defines the surface map,
logical data domains, service boundaries, commercial/trial/entitlement/view-mode
contracts, the data-licensing governance registry, and the enforced Founder↔Social
hard ban. All contracts are **backend-owned**; the frontend owns only presentation.

Source of truth for code: `backend/nexus_platform/` (+ checks) and `tests/platform/`.

## 1. Surface map (four separate products)

| Surface | Purpose | Auth | Notes |
|---|---|---|---|
| **Corporate** | Public marketing + CMS + safe live intelligence | OWNER/admin (RBAC) | No private data; SSE public feed |
| **Personal** | Individual member intelligence product | member auth + entitlements | Intelligence-first; **never** trading execution |
| **Enterprise** | Org/team product (separate) | org auth + RBAC | Not "Personal Advanced+" |
| **Founder Private Trading** | Private execution core | Founder-only, **separate physical DB** | Never exposes positions/PnL/orders/lessons/private AI |

`Personal ≠ Founder Lite`. `Enterprise ≠ Advanced Plus`. View density never authorizes.

## 2. Logical data-domain map

Implemented as schemas/tables inside the existing SaaS PostgreSQL (NOT one physical
DB per domain today). High-volume timeseries may later move to Timescale/ClickHouse
only when justified.

`identity · billing · entitlements · corporate · personal · market · derivatives ·
onchain · news_social · reputation · historical_reaction · enterprise · audit`

Readers per domain — see `backend/nexus_platform/domains.py::DOMAIN_READERS`.
`market` is shared (corporate/personal/enterprise). `news_social` + `reputation`
are Personal/Enterprise only and **never** reachable by Founder-Private.

## 3. Service-boundary & Founder isolation

- **Founder-Private is a separate physical/security boundary.** SaaS surfaces never
  hold its credentials or read its DB (orders/positions/PnL/ledger/lessons/private AI).
- **Social → Founder HARD BAN** (enforced): the Founder trading runtime
  (`domains.FOUNDER_RUNTIME_PACKAGES`) must never import Personal social/KOL/creator
  intelligence (`domains.SOCIAL_BANNED_IMPORT_TERMS`). CI: `test_founder_runtime_has_no_social_imports`
  (checker `checks/founder_social_boundary.py`). Current status: **PASS (0 violations)**.

## 4. Commercial plans + trial (`plans.py`, `trial.py`)

Plan identity = stable `code`; price is metadata, never authorization.

| Plan | Monthly | Annual (−20%) | Notes |
|---|---|---|---|
| FREE | $0 | — | default |
| STARTER | $19.00 | $182.40 | |
| PRO | $39.00 | $374.40 | |
| ADVANCED | $79.00 | $758.40 | |
| ENTERPRISE | custom | custom | contact sales |

- **STARTER_TRIAL_30D**: `trial_started_at = registered_at`, `trial_ends_at = +30d`.
  On expiry: paid entitlements if any, else FREE. **No auto-charge without explicit consent.**
- `effective_plan(now, registered_at, paid_plan)` — paid wins → active trial = starter → free.

## 5. Entitlement capability registry (`entitlements.py`)

`capability × plan → state ∈ {AVAILABLE, LIMITED, COMING_SOON, UNAVAILABLE}`.
Two axes: plan grant (full/limited/none) × backend readiness (ready/coming_soon).

Per **DO NOT IMPLEMENT YET**: only market-derived capabilities are `ready`
(market_overview, watchlist, alerts, history, nex_ai_digest, multi_chart,
custom_workspace, advanced_alerts). Everything needing news/social/derivatives/
on-chain/smart-money/reputation data is `coming_soon` (no licensed data) → the UI
shows COMING_SOON, never fabricated values. `is_allowed` is True only for
AVAILABLE/LIMITED.

## 6. View mode ≠ subscription (`view_modes.py`)

`SIMPLE / STANDARD / PRO` are **presentation** density (answer → +evidence →
+data/tools/controls). `authorizes(view_mode)` is always `False` — authorization is
the entitlement registry. An Advanced subscriber may use Simple; a Starter may see
locked Pro features.

## 7. Data-licensing governance (`data_licenses.py`)

`can_expose_commercially(dataset)` gates commercial exposure. Only
`Exchange market:usdm_public_ticker_ohlcv` is `in_use` (public exchange market data).
Derivatives / on-chain / smart-money / social / news providers are registered as
`not_licensed` → cannot be exposed until licensed. User-facing source labels are
canonical identities (Exchange market / Official / Institution / News / Social) — never
engineering/provider API names. **No provider secrets in this registry or frontend.**
A later PERSONAL-INTEL stage integrates real licensed providers.

## 8. Demo/fixture production audit (baseline for Workstream B)

Personal production currently depends on demo/fixture catalogs for user-facing answers
(checker `checks/personal_demo_dependency.py`):

- `frontend/src/member/firstScreenAnswers.ts` → `./demoCatalog`
- `frontend/src/member/MemberFirstScreen.tsx` → `./demoCatalog`
- `frontend/src/member/intel/index.ts` → `./fixtureCatalog`

**Workstream B must drive this to ZERO**; missing backend capability → UNAVAILABLE /
COMING_SOON, never demo data. Test fixtures stay in isolated test directories.

## 9. Migration design (`0016_platform_foundation.sql`, additive)

Additive-only design for the entitlement/subscription/trial + licensing persistence
(`nexus.subscriptions` with `trial_started_at/trial_ends_at`, `nexus.entitlement_registry`,
`nexus.data_licenses`). Non-destructive; application deferred to when Workstream B/D
needs persisted subscriptions (contracts above are usable stateless meanwhile).

## 10. Remaining licensed-data blockers

Derivatives (OI/funding/liquidation/order-flow), on-chain, smart-money, social/KOL,
news, reputation, historical-reaction — all blocked on commercial licensing. UI is
built with honest COMING_SOON state; no advanced intelligence is claimed available.
