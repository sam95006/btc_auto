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

## 5. Entitlement capability registry (`entitlements.py`) — 1A.1 hardened

Readiness is **not binary**. Four independent dimensions combine to the effective
UI state (most-restrictive wins):

- **plan grant** — full | limited | none
- **backend_state** — ready | partial | absent
- **product_state** — available | beta | partial | coming_soon
- **data_state** — licensed | unlicensed (derived from the licensing registry)

Effective: `UNAVAILABLE` (no grant) → `COMING_SOON` (unlicensed data / not built /
no backend) → `PARTIAL` (backend exists, product partial) → `BETA` → `LIMITED` →
`AVAILABLE`. A capability is **never AVAILABLE just because frontend code exists**.

Audited today (with evidence in `capability_dimensions`):

| capability | backend | product | effective (starter+) |
|---|---|---|---|
| market_overview / watchlist / history | ready | available | **AVAILABLE** (LIMITED free) |
| alerts | partial | partial | **PARTIAL** |
| nex_ai_digest | partial | partial | **PARTIAL** |
| multi_chart / custom_workspace / advanced_alerts | absent | coming_soon | **COMING_SOON** |
| news/social/derivatives/on-chain/smart-money/reputation | absent | coming_soon | **COMING_SOON** (data unlicensed) |

`is_allowed` is True only for AVAILABLE/LIMITED/BETA. Plan authorization and
product readiness remain separate dimensions; UI state is backend-authoritative.

**Enterprise is a SEPARATE product — no inheritance.** Personal capabilities do
NOT grant the Enterprise plan; Enterprise grants are explicit
(`ENTERPRISE_CAPABILITIES` = org_seats / shared_* / org_audit / integrations /
sso). Regression test proves a new Advanced Personal capability never
auto-appears in Enterprise.

## 6. View mode ≠ subscription (`view_modes.py`)

`SIMPLE / STANDARD / PRO` are **presentation** density (answer → +evidence →
+data/tools/controls). `authorizes(view_mode)` is always `False` — authorization is
the entitlement registry. An Advanced subscriber may use Simple; a Starter may see
locked Pro features.

## 7. Data-licensing governance (`data_licenses.py`) — 1A.1 hardened

Explicit, conservative, **fail-closed** gates distinguish RAW redistribution from
DERIVED-intelligence use:

- `can_display_raw_data(ds)` — raw display/redistribution; requires
  `in_use + commercial_use + redistribution_allowed`.
- `can_use_for_derived_intelligence(ds)` — member-safe derived intelligence;
  requires `in_use + commercial_use + derived_data_allowed`.
- `can_cache_dataset(ds)` — requires `in_use + cache_allowed`.
- `requires_attribution(ds)` — unknown datasets default to **True**.
- Unknown/unregistered dataset → **denied** on every gate (public accessibility is
  not a legal right). `can_expose_commercially` kept as the derived-intelligence alias.

Only `Exchange market:usdm_public_ticker_ohlcv` is `in_use` — and it permits
DERIVED use (regime/risk/summaries) but **not** raw redistribution
(`redistribution_allowed = False`), so our product never claims raw-feed rights.
Derivatives / on-chain / smart-money / social / news are `not_licensed`. User-facing
source labels are canonical identities (Exchange market / Official / Institution /
News / Social) — never provider API names. **No provider secrets here or in frontend.**

## 3a. Founder / shared-market clarification (1A.1)

Founder-Private **never** reads a SaaS DB domain directly
(`FOUNDER_DIRECT_SAAS_DB_ACCESS = False`, denied for every domain). It **may**,
where the certified private architecture permits, consume separately-authorized
SAFE market-data **SERVICE** outputs — but only via an **explicit allowlist**
`FOUNDER_SAFE_SERVICE_ALLOWED_DOMAINS = ("market",)`; every other SaaS domain
(identity/billing/entitlements/corporate/personal/derivatives/onchain/news_social/
reputation/historical_reaction/enterprise/audit) and unknown domains are **denied**
by this contract. Social/KOL stays hard-banned. No trading-runtime change.

**Market display semantics (1A.1.1)** — three DISTINCT permissions on the public
exchange dataset: (A) raw continuous-feed **redistribution** = `can_display_raw_data`
→ **DENIED** (not claimed); (B) end-user **snapshot/quote/OHLCV display** =
`can_display_market_snapshot` → **ALLOWED** (evidenced `snapshot_display_allowed`;
public market data — standard permitted display, distinct from feed redistribution);
(C) **derived intelligence** = `can_use_for_derived_intelligence` → **ALLOWED**. Any
dataset lacking explicit evidence fails closed on all three.

**Data-state NOT_APPLICABLE (1A.1.1)** — capabilities with no external dataset
(workspace/seats/SSO/audit/integrations/multi-chart mechanics) are
`NOT_APPLICABLE` and are **not** blocked by licensing; their effective state depends
only on grant/backend/product. Only external-data capabilities are gated by
`licensed | unlicensed` (unknown → unlicensed, fail closed). Enterprise capabilities
no longer misuse `DS_MARKET`.

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
