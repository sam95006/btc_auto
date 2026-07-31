# FOUNDERS DUAL-TRACK REPORT — Unified Control Plane Deploy + Cost Gate Forensic

**Generated:** 2026-07-31  
**Gates:** `DEPLOY_UNIFIED_NEXUS_CONTROL_PLANE=APPROVED` · `DEMO_AUTONOMOUS_24H_BOUNDED_VALIDATION=APPROVED=false`  
**Session audited:** `NEXUS-DEMO-6H-8124394e67`  
**validation_duration=6H** · **post_session_idle_time=separate** · **24H_validation_completed=false**

---

## A 軌 — Unified Control Plane (LIVE)

| Field | Value |
|-------|-------|
| service_name | `nexus-unified-control-plane` |
| service_url | https://nexus-unified-control-plane.zeabur.app |
| service_id | `6a6bf638ffb4fc697c8a7b1f` |
| deployment_commit | `4cadeab` (SPA `/control-plane` fix) |
| deploy_run | `30595915532` (CI smoke raced rollout; live re-smoke PASS) |
| health | 200 |
| overview | 200 |
| `/control-plane` | 200 |
| market_source | Stage3 / `market_intelligence` (LIVE) |
| demo_account_source | Demo Validation / `demo_execution` (`BYBIT_DEMO_PRIVATE_API`) |
| session_source | Demo Validation / `demo_execution` (status=`COMPLETED`) |
| learning_source | Demo Validation federation |
| execution_owner | `DEMO_VALIDATION_SERVICE` |
| execution_owner_count | 1 |
| exchange_write | false |
| stage3_execution_disabled | true |
| mainnet | false |
| real_money | false |
| recommendation | `UNIFIED_NEXUS_CONTROL_PLANE_LIVE_READ_ONLY` — use as single NEXUS entry |

**Must not:** become execution owner · start 24H · exchange write · merge PR #6 · overwrite Stage3 (`6a3b8165…`) or Demo Validation (`6a69ad53…`)

---

## B 軌 — Cost Gate Forensic (COMPLETE)

| Field | Value |
|-------|-------|
| source_db | `/data/nexus_demo_validation/validation.sqlite3` |
| source_checksum | `8e8757ccdfc07efc0f957d0ec75ad54b1862abe766ad9903b0acd84ac801a118` |
| checksum_before == after | true |
| export_run | `30595242637` |
| rows_exported | 1221 |
| unique_candidates | 1221 |
| duplicates | 0 |
| classification_A | 0 |
| classification_B | **1221** |
| classification_C | 0 |
| classification_D | 0 |
| classification_E | 0 |
| formula_mismatch_count | **0** |
| formula_unverifiable_count | 1221 |
| funding_defaulted_zero_count | 0 |
| validated_decision_delta_count | **0** |
| invalid_decision_delta_count | **1221** |
| data_missing_ratio | **1.0** |
| dominant_block_reason | `FEE_RATE_UNKNOWN` (1221/1221) |
| possible_formula_defect | **false** |
| learning_effectiveness | `NOT_YET_OBSERVABLE` |
| 24h_gate_ready | **false** |
| recommendation | `FIX_DATA_SOURCES_THEN_DRY_RUN_REPLAY` |

### Root cause (verified from Persistent Volume, readonly)

Every cost-gate row short-circuited here:

```text
fee_rate is None or <= 0  →  FEE_RATE_UNKNOWN  →  empty breakdown  →  synthetic zeros on net/cost fields
```

- `writer.fetch_fee_rate(symbol)` returned unknown for all evaluated candidates (`/v5/account/fee-rate`).
- Cost math (fee/slippage/funding/buffer/net R:R) **never ran**.
- Candidate stream **does** carry real `funding_rate` values (many non-zero); those were never applied because fee gate failed first.
- Recorded `estimated_* = 0.0` on these rows are dataclass defaults, not computed costs — treat as honesty noise on early exit, not “zero market cost”.

### Decision Delta semantics

| Check | Result |
|-------|--------|
| `source_trade_case_id` | empty on 1221/1221 |
| `before_verdict == after_verdict` | 1221/1221 (`ALLOW`) |
| `similarity_score == 0` | 1221/1221 |
| Valid learning deltas | **0** |

`decision_delta_count == candidates_total` is **misclassification**: scan-session memory applies, not trade-learning deltas. Do not count toward learning effectiveness.

### Next step (not 24H)

Per Founder rule for dominant **B**:

1. Fix fee-rate data source / auth / API path for Demo Validation (readonly diagnose first).
2. Preserve honesty: early-exit must not look like computed zero costs.
3. Reclassify decision_delta persistence so gate blocks ≠ learning deltas.
4. Dry-run / shadow replay — **do not** open 24H.

---

## Explicit non-claims

- Service uptime after 16:56 Taiwan ≠ validation duration.
- System has **not** completed 24H trading validation.
- Do **not** claim 24H PASS.
