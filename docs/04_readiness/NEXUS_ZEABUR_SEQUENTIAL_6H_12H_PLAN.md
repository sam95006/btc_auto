# NEXUS Sequential Demo Validation Plan (Zeabur)

**Status:** Preparation only — 24H operational observation still open until `2026-08-01T05:11:30Z`.

## Order (must not invert)

1. Complete 24H single-service operational observation  
2. PASS → delete legacy Stage3 + Control Plane cards  
3. Verify Zeabur service count = 1  
4. Deploy 6H/12H test build to **existing** Validation (not yet)  
5. Run 6H V2  
6. 6H hard PASS → Run **new** 12H V3 session  
7. Stop before 24H trading gate  

## PR #24

| Field | Value |
|-------|-------|
| mergeable (re-checked) | **true** / `CLEAN` (earlier `false` was transient / stale) |
| conflict_count | **0** after merge of consolidation tip including T+3H |
| draft | true |
| deploy | false |
| live_effect | false |

## Added control surfaces

- `v2_session_state.py` — state machine (no deadline extend / no COMPLETED→RUNNING)
- `v2_bounded_engine.py` — 6H/12H engines, distinct session ids
- `v2_kill_switch.py` / `v2_session_recovery.py`
- `v3_policy.py` / `v3_start_gate.py`
- workflows: `demo_autonomous_6h_v2_zeabur.yml`, `demo_autonomous_12h_v3_zeabur.yml`  
  (refuse live write while observation open; phrase-gated)

## Conditional Founder gates

- `DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION` — CONDITIONALLY_APPROVED, not started  
- `DEMO_AUTONOMOUS_12H_V3_BOUNDED_VALIDATION` — CONDITIONALLY_APPROVED, not started  
- Next after both: `DEMO_AUTONOMOUS_24H_BOUNDED_VALIDATION` — **not** auto-opened  

## Runtime freeze

Validation remains on `598a5e1` / deploy `30605493505` until observation finalization.
