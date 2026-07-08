# Stage 4.18-N Zeabur Clean Redeploy and Runtime Ready Report

**Generated:** 2026-07-08T03:56:00Z  
**Branch:** `stage3-demo-learning`  
**Base commit:** `8230f73`  
**Service:** `nexus-stage3-bybit-demo-learning`  
**Verdict:** `STAGE_4_18N_REDEPLOY_RUNTIME_READY` — stopped at gate; **N-R1 30m not started**

---

## 1. Root cause

After Zeabur subscription renewal, the Stage 3 service was **SUSPENDED / CRASHED** with `/health=502` and `service exec=CONTAINER_NOT_FOUND`.

Two independent blockers were found:

1. **Stale / incomplete deploy package**
   - Missing `run_stage3_demo_order_background.sh` and `run_stage3_24h_demo_learning_background.sh` caused Docker build `chmod` failure (`FAILED` deployments).
   - Deploy package lacked full **4.18-N** markers until clean rebuild from `8230f73`.
   - `stage4_provider_field_compliance_review.py` was missing from build allowlist.

2. **Zeabur variables wiped**
   - After suspension, only `STAGE4_CLOUD_DRY_RUN_MINUTES=0` remained.
   - Credentials and Stage 3/4 safety vars were restored from local `.env`.
   - Stage 4 readonly strict-env required `PAPER_ONLY=true` and `BYBIT_SHADOW_MODE=true` (not the demo-learning defaults `false`).

---

## 2. Clean build result

| Item | Result |
|------|--------|
| Build script | `tools/research/build_zeabur_stage3_demo_learning_deploy_package.py` |
| `package_ready` | `true` |
| `package_file_count` | `133` |
| `STAGE3_DEPLOY_VERSION.commit` | `8230f73d623e0b55005ad88b182c450e40cb5e71` |
| Background scripts restored | `run_stage3_demo_order_background.sh`, `run_stage3_24h_demo_learning_background.sh` |
| Build guard added | Fail fast if background scripts missing before wipe |

---

## 3. Deploy package marker check (post-rebuild)

| Marker | Present |
|--------|---------|
| `stage_marker=4.18-N` | yes (`check_stage4_runtime_version.py`) |
| `GROQ_STRICT_OUTPUT_RULE` | yes (`stage4_prompt_builder.py`) |
| `CEREBRAS_STRICT_OUTPUT_RULE` | yes (`stage4_prompt_builder.py`) |
| `apply_cosmetic_field_normalization` | yes (`stage4_schema_repair.py`) |
| `stage4_provider_field_compliance_review.py` | yes |
| `stage4_schema_repair.py` | yes |

---

## 4. Sync script check

`tools/research/sync_418f_runtime_to_zeabur.py` already includes all required 4.18-N files (17 paths), including:

- `stage4_cerebras_payload.py`
- `stage4_provider_chain.py`
- `stage4_provider_field_compliance_review.py`
- `stage4_schema_repair.py`
- `check_stage4_runtime_version.py`

No sync script change required this round.

---

## 5. Deploy result

| Item | Value |
|------|-------|
| Deployment ID | `6a4dc5926ec90535ce442acb` |
| Build | **SUCCESS** (image ~85MB) |
| Initial runtime | **CRASHED** — strict-env: `PAPER_ONLY`, `BYBIT_SHADOW_MODE` not true |
| Fix applied | `variable update PAPER_ONLY=true BYBIT_SHADOW_MODE=true` + `service restart` |
| Post-fix status | **RUNNING** |

---

## 6. Runtime patch sync result

```
python tools/research/sync_418f_runtime_to_zeabur.py
```

| Item | Value |
|------|-------|
| Files synced | 17 |
| `all_files_synced` | `true` |
| Patch dir | `/data/stage4_418f_runtime_patch` |

---

## 7. Runtime gate result

```json
{
  "runtime_version_check_passed": true,
  "stage_marker": "4.18-N",
  "prompt_hints_present": true,
  "app_file_stale_suspected": false,
  "schema_enforcement_present": true
}
```

---

## 8. Health check result

```
GET https://nexus-stage3-bybit-demo-learning.zeabur.app/health
HTTP/1.1 200 OK
{"ok":true,"read_only":true,"service":"stage3-readonly-web"}
```

---

## 9. Safety variables (Zeabur)

| Variable | Value |
|----------|-------|
| `STAGE3_STARTUP_MODE` | `idle` |
| `OPERATOR_GO_STAGE3_24H_RUNNER` | `false` |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` | `0` |
| `STAGE4_ORDER_ALLOWED` | `false` |
| `STAGE4_ALLOW_MOCK_FALLBACK` | `false` |
| `STAGE4_REQUIRE_REAL_LLM` | `true` |
| `STAGE4_DRY_RUN_ONLY` | `true` |
| `STAGE4_REQUIRE_STAGE3_CONTEXT` | `true` |
| `BYBIT_ORDER_ALLOWED` | `false` |
| `EXCHANGE_WRITE_ALLOWED` | `false` |
| `PRIVATE_ORDER_ENDPOINT_BLOCKED` | `true` |
| `PAPER_ONLY` | `true` (Stage 4 readonly strict-env) |
| `BYBIT_SHADOW_MODE` | `true` (Stage 4 readonly strict-env) |
| `NEXUS_ARM_ALLOWED` | `false` |
| `NEXUS_RADAR_AUTO_TRADE` | `0` |
| `ZEABUR_PRODUCTION_RUNNER_ALLOWED` | `false` |

Credentials restored via `setup_zeabur_stage3_service.py --skip-deploy` (keys not logged).

---

## 10. N-R1 readiness

| Gate | Status |
|------|--------|
| Service RUNNING | pass |
| `service exec echo OK` | pass |
| `/health` 200 | pass |
| Runtime gate `4.18-N` | pass |
| `STAGE4_CLOUD_DRY_RUN_MINUTES=0` | pass |
| Safety variables | pass |

**N-R1 30m can be retried** after explicit operator approval. This report stops at gate.

---

## 11. Safety confirmation

- No orders sent
- No demo order
- No paper order execution
- No ARM / radar / production / btc-auto
- No 30m / 60m soak started
- No Stage 4.19 started
- No `/data`, jsonl, logs, bundles, or secrets committed

---

## 12. Files changed this round

- `tools/research/build_zeabur_stage3_demo_learning_deploy_package.py` — add `stage4_provider_field_compliance_review.py`; fail if background scripts missing
- `deploy/zeabur_stage3_demo_learning/` — clean rebuild with 4.18-N code + restored background scripts
- `docs/reports/STAGE_4_18N_REDEPLOY_AND_RUNTIME_READY_REPORT.md` — this report

---

## 13. Next step recommendation

1. Operator confirms this report (`RUNNING` + health 200 + runtime gate `4.18-N` PASS).
2. Then run **Stage 4.18-N-R1** 30m provider-schema regression soak with `STAGE4_CLOUD_DRY_RUN_MINUTES=30` (reset to `0` after soak).
3. Do **not** start Stage 4.19 until N-R1 field-contract review passes.
