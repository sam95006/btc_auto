# NEXUS Public Mobile Notification & Widget Architecture V1 (PUB-K)

Status: **LOCAL_OR_STAGING_ONLY / NON_PRODUCTION / ARCHITECTURE_PROTOTYPE**

Branch: `feature/public-v1-mobile-notification-widget`  
Base: `39e6b1ae1a40698d02c4cb8de4d80fc412309cfc`

## Purpose

Provide architecture and executable prototypes for member mobile alerts,
push delivery stubs, iOS Live Activity / Widget abstractions, Android Widget
abstractions, preference controls, and deep-link routing.

This lane does **not** ship production push credentials, store submissions,
or live public deployment.

## Surfaces

```
Public Decision Cloud / Realtime Transport
        │
        ▼
 Mobile Notification Foundation (PUB-K)
   ├─ Alert builders (Decision / Risk / Stale / Thesis / Anomaly)
   ├─ Preference gate
   ├─ Deep-link router (nexus://app/…)
   ├─ Push provider (STUB | MOCK_IN_MEMORY | LOCAL_FILE_SINK)
   ├─ iOS Live Activity abstraction
   ├─ iOS Widget timeline abstraction
   └─ Android Widget abstraction
        │
        ▼
 Flutter app (PUB-J) / Member Web notification settings (PUB-D)
```

## Alert kinds

| Kind | Intent |
|------|--------|
| `DECISION_STATUS` | Decision lifecycle / state change |
| `RISK` | Public risk condition |
| `DATA_STALE` | Freshness degradation (must not conceal stale) |
| `THESIS_INVALIDATED` | Thesis monitor invalidation |
| `MARKET_ANOMALY` | Public market anomaly signal |

Every alert carries lineage: `source_system`, `as_of`, `retrieved_at`,
`freshness`, `completeness`, `lineage_id`, `mode`.

LIVE mode refuses fabricated / DEMO_DATA freshness concealment.

## Push providers

Allowed:

- `STUB` — no network
- `MOCK_IN_MEMORY` — test / local demo sink
- `LOCAL_FILE_SINK` — local JSON envelopes

Refused:

- Production APNs keys / certs
- Production FCM server keys
- `PUSH_PRODUCTION_ENABLED=true`
- Device `app_environment=production`

## Widgets / Live Activities

Abstractions return structured prototypes only. They do **not** invoke
ActivityKit, WidgetKit, or Android `AppWidgetManager`.

## Deep links

Scheme: `nexus://app/{route}?…`

Member routes only (Home, Markets, Decisions, …, Notification Settings).
Private founder / execution / wallet / checkpoint routes are hard-banned.

## Hard bans (lane)

- No production notification credentials
- No App Store / Google Play submission
- No live public deployment / live billing
- No private-core imports
- No private fields in notification payloads
- No fabricated live alerts
- No lane `*_status.json`
- No PR #26 / #27 merge

## Owned paths

- `backend/nexus_public_mobile_notify/`
- `mobile/nexus_notify_prototypes/`
- `tests/public_mobile_notify/`
- `docs/mobile/`

## Verification

```bash
python -m pytest tests/public_mobile_notify -q
```

## Pass-2 hardening

- Deep links validated on every `dispatch` (private routes hard-banned)
- Quiet hours enforced (CRITICAL may pierce)
- Delivery statuses limited to STUB / MOCK / FILE_SINK acknowledgements
- Machine-verifiable security invariants (`collect_security_invariants`)
- No lane `*_status.json`; no production credential markers in owned paths
