# P2 Migration End-to-End Root-Cause Audit

**Date:** 2026-08-21  
**Main at audit start:** `c5add473bdc047ad57f21763b381396e3599dbad`  
**Scope:** Founder-approved staging Postgres P2 migration 0007 only  
**Hard constraints honored:** no workflow dispatch, no P2.1 live qualification, no P1 rerun, no Bybit orders, no PostgreSQL mutation, no Mainnet/Demo ARM changes

---

## 1. Authoritative Run #8 result

| Gate | Result |
|------|--------|
| Offline tests | PASS (prior commit suite) |
| Migration context build | PASS |
| Run-scoped create + single deploy | PASS |
| Runtime variable injection | PASS |
| Baked-SHA service-exec readiness | FAIL — 12/12 `NOT_RUNNING_SERVICE` |
| `current_image_streak` | 0 |
| `current_image_positive_proof_count` | 0 |
| `P2_MIGRATION_DEPLOYMENT_CONVERGED` | false |
| Atomic migration apply | SKIPPED |
| `P2_MIGRATION_PYTHON_STARTED` | false |
| Migration 0007 applied | **NO** — still pending |

PostgreSQL must continue to be treated as:

- applied: `0001..0006`
- pending: `0007`

---

## 2. What service-exec `NOT_RUNNING_SERVICE` does *not* prove

The control plane previously jumped from “deploy CLI returned” to “service exec for baked SHA”.

`zeabur service exec` returning:

```text
ERROR execute command failed
code=NOT_RUNNING_SERVICE
This service is not in the running state
```

does **not** distinguish:

| State | Meaning |
|-------|---------|
| BUILDING | Image still installing deps / building |
| DEPLOYING | Build finished; runtime not yet ready |
| BUILD_FAILED | Build error; never starts |
| RUNTIME_CRASH | Process exits after start |
| HEALTHCHECK_FAILED | Process up but platform marks unhealthy |
| SUSPENDED / INACTIVE | Platform stopped the service |
| Slow start | Still provisioning beyond the exec probe window |

**Inference ban:** do not attribute Run #8 to stale pods, second deploy, health-server metadata, Docker syntax, or env injection without deployment status/log evidence.

---

## 3. Workflow DAG audited (pre-diagnostic → post-diagnostic)

### Pre-diagnostic DAG (Run #8)

1. Confirm intent  
2. Offline pytest (narrow P2 suite)  
3. Secret presence  
4. Build `/tmp/p2_migration_ctx`  
5. `zeabur deploy --create` from migration context (single deploy)  
6. Inject runtime vars including DSN  
7. **Immediate** baked-SHA `service exec` loop (12 × 5s)  
8. Downstream skipped on fail

### Gap

No `zeabur deployment get` / `deployment log -t=build|runtime` before service exec → blind `NOT_RUNNING_SERVICE`.

### Corrected DAG (this change)

1–6 unchanged in intent  
7. **NEW:** bounded wait on deployment status/logs; allow service exec only when classified `RUNNING`  
8. Existing positive-proof baked-SHA service-exec loop (`MAX_ATTEMPTS=12` unchanged)  
9. Downstream gates unchanged (stdout authoritative, file audit-only, atomic same-exec)

---

## 4. Image / bootstrap static audit (offline)

Migration image contract (no live container required for this audit):

| Check | Status |
|-------|--------|
| Entrypoint starts `migration_health_server.py` | Yes |
| Bind `0.0.0.0` | Yes (`bind_host=0.0.0.0`) |
| `PORT` from Zeabur `PORT` | Yes |
| `DEPLOYMENT_COMMIT` / `SOURCE_COMMIT` baked | Yes (context builder) |
| `p2_staging_migration_0007.py` present in context | Yes |
| `NEXUS_POSTGRES_URL` not baked into Dockerfile | Yes |
| Exchange flags default false | Yes |
| Full `requirements.txt` pip install in image | Yes — **plausible long BUILDING duration** |

Health metadata previously hardcoded `nexus-p2-migration-0007` while runtime names are `nexus-p2m7-<run>-<attempt>`. That mismatch is **not** evidence for `NOT_RUNNING_SERVICE`; metadata is now run-scoped/generic without changing listen/startup behavior.

**Do not change global `requirements.txt`.** If build logs later prove pip duration is the blocker, evaluate a migration-specific minimal dependency set in a separate founder directive.

---

## 5. Historical P1→P2 regression lock

An immutable offline gate now runs the existing certified suites together via:

`python -m tools.ci.p2_historical_p1_p2_regression_lock`

Covered surfaces include (existing tests only):

- P1 Run8 atomic / postgres accounting recovery / rollout / identity probes  
- P1 `closed_at` TIMESTAMPTZ  
- P1 durable order foundation / ledger  
- P1 migration 0006  
- P1 Zeabur transport / validation runtime  
- P2 Run8 learning closure / durable lesson store / evidence truth  
- P2.1 Process-B pre-write restart qualification  
- P2 migration 0007 offline + atomic/bootstrap/readiness/file-channel  

Future P2 migration workflow offline step **must** fail if this lock fails.

Certified live P1 outcomes remain immutable evidence — not re-executed.

---

## 6. Freeze boundary

**Do not edit during migration transport diagnosis (unless founder expands scope):**

- `backend/nexus_demo_execution` P1 execution/recovery  
- migrations `0001..0006`  
- P1 Founder workflows  
- Bybit adapters / order execution  
- Run8 certified evidence artifacts  
- P2 reflection / durable lesson / Process-B semantics  

**Allowed:**

- `.github/workflows/founder_approved_staging_postgres_p2_migration.yml`  
- `tools/ci/p2_migration_*` + historical lock helper  
- `deploy/zeabur_p2_migration_0007/*`  
- migration-specific tests + this audit doc  

---

## 7. Diagnostics implemented (evidence path for next run)

Before any baked-SHA service exec:

1. `zeabur deployment get --json`  
2. `zeabur deployment list --json`  
3. `zeabur deployment log -t=build`  
4. `zeabur deployment log -t=runtime`  

Classifier emits sanitized:

- `P2_MIGRATION_DEPLOYMENT_STATUS`  
- `P2_MIGRATION_BUILD_STATUS`  
- `P2_MIGRATION_RUNTIME_STATUS`  
- `P2_MIGRATION_BUILD_LOG_TAIL`  
- `P2_MIGRATION_RUNTIME_LOG_TAIL`  

State machine:

| Status | Action |
|--------|--------|
| BUILDING / DEPLOYING | wait (deployment-level timeout) |
| RUNNING | proceed to baked-SHA service-exec probes |
| FAILED / RUNNING_THEN_CRASHED / SUSPENDED | fail closed with log tails |
| UNKNOWN after wait timeout | fail closed with diagnostics |

Service exec remains deferred until `RUNNING`.

---

## 8. Current best working hypothesis (not yet proven)

**Most likely class:** deployment still `BUILDING` or `DEPLOYING` (full `requirements.txt` install) when the 12× service-exec loop ran — or build/runtime failed without the workflow reading logs.

**Not proven until next run captures deployment get/log tails.**

**Ruled out as primary explanation without evidence:** multi-pod stale SHA TOCTOU (already fail-closed correctly on empty baked SHA), file-channel 200/0 (already demoted), Python package entrypoint (already fixed), fixed-name service reuse (already run-scoped).

---

## 9. Safety posture

- `MAINNET=false` / `REAL_MONEY=false` / `DEMO_AUTONOMOUS_ENABLED=false` / `AUTONOMOUS_SEND=false` / `EXCHANGE_WRITE=false`  
- Zero exchange writes in migration helpers and lock suites  
- No ARM changes  
- P1 schema `0001..0006` unchanged  
- Global `requirements.txt` unchanged  

---

## 10. Next founder action

Do **not** dispatch until this commit is reviewed.

On the next approved dispatch, treat deployment diagnostic JSON/log tails as the authoritative root-cause source before any further transport or timeout changes.
