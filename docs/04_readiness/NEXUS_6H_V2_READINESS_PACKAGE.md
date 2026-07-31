# NEXUS Demo Autonomous 6H V2 Readiness

**Gate approved for preparation only:** `PREPARE_DEMO_AUTONOMOUS_6H_V2_READINESS`  
**Live start gate:** still `DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION=false`

| Field | Value |
|-------|-------|
| worktree | `C:\Temp\BTC_BOT_6H_V2_READINESS` |
| branch | `feature/demo-autonomous-6h-v2-readiness` |
| base | `feature/nexus-single-service-consolidation` @ `a90fb0c` |
| draft_pr | pending create |
| deploy | **false** |
| live_effect | **false** |
| exchange_write | **false** |
| runtime_sot_commit | `598a5e11985f613007c8d65e61fa1dd9c7cbdf67` |

## Deliverables

- `backend/nexus_demo_execution/v2_policy.py`
- `v2_session_controller.py` (dry-run default)
- `v2_decision_delta.py` (honest learning deltas)
- `v2_six_role.py` / `v2_evidence_schema.py`
- `tools/ci/demo_6h_v2_preflight.py`
- `tools/ci/demo_6h_v2_dry_run.py`
- `tools/ops/delete_legacy_services_after_observation.py` (dry-run default)
- `tests/test_demo_6h_v2_readiness.py`
- `.github/workflows/demo_6h_v2_readiness.yml`
- `frontend/src/pages/SixHV2ReadinessPage.tsx` (not deployed to frozen runtime)

## Explicit non-actions

- No Validation redeploy / env / fee / R:R change
- No 6H V2 start
- No legacy delete execute
- No Mainnet / Real Money

## Recommendation (prep checkpoint)

`NEXUS_6H_V2_READINESS_DRAFT_READY_FOR_REVIEW` once Draft PR + CI green; live start still blocked until observation PASS + separate Founder gate.
