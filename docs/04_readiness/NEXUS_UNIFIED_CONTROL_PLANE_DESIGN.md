# NEXUS Unified Control Plane — Design

**Status:** Draft code only · `deploy=false` · `live_effect=false` · `exchange_write=false`  
**Branch:** `feature/unified-nexus-control-plane`  
**Exact base:** `2a647695e9cc6f90d54a92ce5c35fd8de3000aea`  
**Stacked on:** `feature/bybit-demo-execution-validation` (PR #6 remains Draft)

## Goal

One user-facing NEXUS site (Overview / Market / Demo / Performance / Learning / Health) while keeping backend workers isolated:

```
NEXUS Web / Control Plane
├── Market Intelligence Service  (Stage3 — read market only)
├── Demo Execution Service       (Validation — sole execution owner)
├── Position Supervisor          (Validation)
└── Learning / Reflection        (Validation evidence)
```

## Version separation (mandatory)

| Label | SHA | Meaning |
|-------|-----|---------|
| `pr6_branch_head` | `2a647695e9cc6f90d54a92ce5c35fd8de3000aea` | Git tip of PR #6 branch / Control Plane base |
| `observation_deployed_code_sha` | `9b6f57c1bc3afe988f0fc3829f62dad2ee510156` | Frozen Zeabur 6H observation runtime |
| `deploy_run` | `30509623012` | Observation deploy that started 6H |

These must never be conflated as one "runtime version".

## Contracts

- `execution_owner = DEMO_VALIDATION_SERVICE` (single owner)
- `stage3_execution_owner = false`
- `stage3_exchange_write = false`
- `stage3_auto_send = false`
- Control Plane federation: **GET only**
- Field envelope: `value`, `source_service`, `source_timestamp`, `freshness_sec`, `data_status`, `evidence_ref`
- `data_status ∈ {LIVE, STALE, MISSING, UNKNOWN, UNAVAILABLE, SERVICE_UNAVAILABLE, SCHEMA_MISMATCH}`
- No synthetic `0` / `[]` / `NONE` pretending a successful read
- On Demo Execution down: `EXECUTION_SERVICE_UNAVAILABLE` — never fall back to Stage3 trade/account state

## Security

- Host allowlist from backend env (`NEXUS_STAGE3_URL` / `NEXUS_DEMO_VALIDATION_URL`)
- Request timeout, circuit breaker, response size limit, schema object check
- SSRF block for unknown hosts / metadata IPs
- Secret redaction on federated payloads
- Browser must not hardcode multi-service URLs

## Non-goals this sprint

- No Zeabur redeploy of 6H observation service
- No Stage3 retirement execution
- No merge of PR #6 or Control Plane
- No Mainnet / Real Money
- No 24H auto-start

## Hardening (PR #23)

- Canonical envelope: `source_role`, `received_at`, `freshness_seconds`, `schema_version`, `NOT_APPLICABLE`
- Ownership contract: single `DEMO_VALIDATION_SERVICE`; Stage3 permanently execution-disabled
- Why-no-trade Gate Breakdown + cost-gate diagnosis (analysis only)
- Learning evidence chain UI + effectiveness labels (no PROVEN/PROFITABLE)
- Version labels keep `pr6_branch_head` ≠ `observation_deployed_code_sha`
- Federation counters + write-route 405
- Browser / mobile / a11y / in-process container smoke + CI workflow
- `tools/analysis/finalize_demo_6h_session.py` for post-deadline readonly finalize
- Scope frozen: `pr23_scope_frozen=true`, still `deploy=false`