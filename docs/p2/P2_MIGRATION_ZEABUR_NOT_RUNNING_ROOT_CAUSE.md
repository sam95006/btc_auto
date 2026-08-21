# P2 Migration — Zeabur `NOT_RUNNING_SERVICE` Root-Cause Report

**Date:** 2026-08-21  
**Main at investigation:** `1898ee22f5ea1dd884505561e8dc0d550f228234`  
**Constraint:** report only — no workflow dispatch, no migration SQL change, no operational-readiness logic change, no retry expansion

---

## Authoritative latest run symptom

| Gate | Result |
|------|--------|
| Metadata diagnostic | PASS (`P2_MIGRATION_METADATA_PROCEED_TO_OPERATIONAL=true`) |
| Structured service Status | `UNKNOWN` |
| Operational service-exec | 12/12 `P2_MIGRATION_SERVICE_NOT_RUNNING_YET=true` |
| Positive image proofs | 0 |
| `P2_MIGRATION_PYTHON_STARTED` | false |
| Migration 0007 | **NOT APPLIED** |

Zeabur exec error class (unchanged across runs):

```text
ERROR execute command failed
code=NOT_RUNNING_SERVICE
This service is not in the running state
```

Official Zeabur command-execution docs require an active/running service container.
`NOT_RUNNING_SERVICE` means: **no running workload in the environment targeted by `service exec`**.

---

## ZEABUR_SERVICE_NOT_RUNNING_ROOT_CAUSE

### Primary root cause (code-proven)

**`zeabur deploy --create` is invoked without `--environment-id`, while every later control-plane call targets the workflow’s fixed staging env via `--env-id $ZEABUR_ENV_ID`.**

Evidence:

1. Current bootstrap plan (`tools/ci/p2_migration_bootstrap.py` → `plan_single_create_deploy`):

```text
zeabur deploy --create --name <run-scoped> --project-id <project> -i=false --json
```

   - **Missing:** `--environment-id <ZEABUR_ENV_ID>`
   - Offline proof on this commit: `has_environment_id=False`, `has_env_id=False`

2. Installed CLI contract (`zeabur deploy --help`) documents:

```text
--environment-id string   Environment ID to redeploy on
```

3. Workflow always uses staging env for post-create operations:

```text
ZEABUR_ENV_ID: 69d559b6474db8a99d6dd6bf
variable create/update --env-id $ZEABUR_ENV_ID
service get --env-id $ZEABUR_ENV_ID
service exec --env-id $ZEABUR_ENV_ID
deployment get/log --env-id $ZEABUR_ENV_ID
```

### Why this matches observed runtime

| Observation | Explanation under env mismatch |
|-------------|--------------------------------|
| Create/deploy CLI returns service id | Service object created in project; deploy may bind a **different/default** environment |
| `service get` → `Status=UNKNOWN` | Staging env has no running deployment for that service |
| Build log: container-image / N/A | Staging env has no Zeabur build stream for a workload that never started there |
| 12/12 `NOT_RUNNING_SERVICE` | Exec correctly refuses when staging has no running container |
| Metadata proceeds (UNKNOWN not veto) | New control model correctly demotes UNKNOWN; cannot invent RUNNING |
| Operational readiness never progresses | Waiting for exec cannot succeed if the wrong env never has a pod |

This is **not** fixed by more readiness retries, more metadata sources, or classifier tweaks.

---

## CREATE_DEPLOY_RESULT

| Item | Finding |
|------|---------|
| Command | `zeabur deploy --create --name nexus-p2m7-<run>-<attempt> --project-id … --json` from migration context cwd |
| Service ID | Resolved (create step PASS historically) |
| Environment targeting | **Not specified** |
| Deployment state in staging | Consistent with **no running staging deployment** (`Status=UNKNOWN`, empty/unusable deployment tokens) |
| Workload/pod in staging | **Absent for exec purposes** (`NOT_RUNNING_SERVICE`) |
| Health server on Zeabur | **Not observable via exec** while not running in target env |

---

## SERVICE_TYPE_RESULT

| Item | Finding |
|------|---------|
| Create path | Dockerfile + entrypoint health server (persistent process intended) |
| Exec support | Zeabur `service exec` exists and is used elsewhere (P1) successfully **on services that are running in the same env** |
| Precondition | Docs + CLI behavior: service must be in running state |
| Conclusion | Service type is appropriate for exec **once a running container exists in the targeted environment**. Current create does not prove that staging env ever receives that running container. |

---

## CONTAINER_STARTUP_RESULT

Static image/entrypoint audit (no SQL, no exchange):

| Check | Result |
|-------|--------|
| Entrypoint → `migration_health_server.py` | Yes |
| Bind `0.0.0.0:$PORT` | Yes |
| Exits on missing Postgres URL | **No** (health server does not require DSN) |
| Safety flags forced false in entrypoint | Yes |
| `DEPLOYMENT_COMMIT` / `SOURCE_COMMIT` baked | Yes |

Local process contract (Docker unavailable on this host; ran health module directly):

| Check | Result |
|-------|--------|
| Health HTTP 200 | Yes |
| Safety flags false in JSON | Yes |
| Remained responsive ≥ 60s | Yes |
| Exited spontaneously | No |

So **application startup is not the primary failure**. The platform never exposes a running staging container to exec.

---

## ENV_VAR_RESTART_EFFECT

| Item | Finding |
|------|---------|
| Workflow order | create/deploy → **then** many `variable create/update` including `NEXUS_POSTGRES_URL` |
| Explicit restart after inject | **None** in P2 migration workflow |
| Contrast | Several other NEXUS workflows call `zeabur service restart --env-id …` after variable changes |
| Effect if env mismatch | Variables are written to staging while any create-time workload may sit elsewhere; staging remains not-running |
| Effect if env matched later | Variable updates may trigger platform restart/redeploy; without an explicit restart + wait, timing can still yield transient NOT_RUNNING — secondary risk only |

Primary blocker remains **create without `--environment-id`**, not “health server exits after env inject.”

---

## SERVICE_EXEC_SUPPORT_RESULT

| Item | Finding |
|------|---------|
| CLI | `zeabur service exec --id … --env-id …` is supported |
| Required condition | Service running in that environment |
| Latest run | Condition never met (12 consecutive NOT_RUNNING) |
| Inference | Exec transport is fine; **target env has no running instance** |

---

## LOCAL_CONTAINER_60S_RESULT

| Item | Result |
|------|--------|
| Docker engine on audit host | **Unavailable** (`docker` not installed / not on PATH) |
| Equivalent local health-server run | **PASS** — alive ≥ 60s, `/health` 200, flags false |
| Full Dockerfile image build locally | **Not executed** (no Docker) |

---

## Recommended next fix (NOT applied in this report)

1. Pass `--environment-id "$ZEABUR_ENV_ID"` into `zeabur deploy --create` (bootstrap plan + ensure service).  
2. Capture sanitized create JSON: service id, environment id, deployment id/state.  
3. After var inject, optionally `service restart --env-id` once, then operational readiness (still no retry inflation beyond existing budget).  
4. Do **not** invent metadata RUNNING; keep operational exec as readiness authority.

---

## Freeze / lock

Historical lock and certified-surface freeze must remain PASS after this documentation-only commit.
