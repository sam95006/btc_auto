# NEXUS Demo Autonomous 6H Bounded Validation — INTERIM

**Status:** RUNNING (frozen cohort — do not redeploy)

| Field | Value |
|-------|-------|
| session_id | NEXUS-DEMO-6H-8124394e67 |
| session_started_at | ~2026-07-30T02:56:16Z (unix 1785380176.29) |
| deployment_commit (env NEXUS_DEPLOYMENT_ID) | 92a89dfaa8cc… (workflow ref) |
| code_sha (deploy checkout) | 9b6f57c1bc3afe988f0fc3829f62dad2ee510156 |
| deploy_run | 30509623012 |
| policy_version | demo-autonomous-6h-bounded-v1 |
| account_epoch | epoch-0001 |
| starting_wallet | 5023.01131876 |
| starting_equity | 5023.01131876 |
| T0 candidates | 8 |
| T0 cost_gate_blocks | 8 |
| T0 entries | 0 |

## Notes
- All initial candidates blocked by cost-adjusted gate (fail-closed; likely FEE_RATE_UNKNOWN or insufficient net edge). Zero entries is a valid interim state.
- Version freeze active: no redeploy until session completes.
- Monitor: 15-minute checkpoint polls → `artifacts/demo_validation_6h/`

## Final report
Will be written to this path on session end with full Founder metrics.
