# P1 / P2 historical evidence preservation (2026-08-24)

**Scope of this commit:** Validation service-id source-of-truth, GitHub-native Full Engine packaging, 6H workflow CTX removal, deployment identity via GitHub SHA.

**Not in scope:** decision / risk / learning / reflection / penalty / execution / PnL math.

## Verdict

| Marker | Value |
|--------|-------|
| `P1_HISTORICAL_EVIDENCE_PRESERVED` | **yes** |
| `P2_HISTORICAL_EVIDENCE_PRESERVED` | **yes** |
| `FULL_P1_RERUN_REQUIRED` | **no** |
| `FULL_P2_RERUN_REQUIRED` | **no** |

## Semantics check (packaging-only delta)

| Surface | Changed? | Evidence |
|---------|----------|----------|
| Decision semantics | no | No edits under P1 qualification / decision engines |
| Risk semantics | no | No certified risk / RMG logic edits |
| Learning semantics | no | No `certified_learning` / lesson store edits |
| Reflection semantics | no | No reflection pipeline edits |
| Penalty / repeat-mistake | no | No P2 guard edits |
| Execution semantics | no | No `DurableOrderLedger` / submit-after-persist edits |
| Performance / PnL calculations | no | No `pnl_reconcile` edits |

Frozen surfaces from prior certified commits (`a3a7bb8`, `8558b28`) remain the P1/P2 evidence baseline. This change set is deployment routing + Docker packaging.

## What did change (non-semantic)

- Confirmed Validation service id: `6a82a79aa21454a2cf6b0015`
- Obsolete candidate `6a69ad539949111176cefe63` is forbidden as a Validation target
- `Dockerfile.full_engine` builds from repository-root context
- 6H workflow deploys GitHub `main` with `ZBPACK_DOCKERFILE_PATH` (no `/tmp/6h_v2_ctx`)
