# NEXUS Unified Control Plane — Test Report

**PR:** #23 (`feature/unified-nexus-control-plane`)  
**Base:** `feature/bybit-demo-execution-validation`  
**Observation cohort:** preserved (`redeploy=0`, untouched)

## Results (local hardening run)

| Suite | Result |
|-------|--------|
| `tests/test_unified_nexus_control_plane.py` | **14 passed** |
| `tools/ci/control_plane_docker_smoke.py` | **PASS** (`overview_200`, `write_blocked`, `secret_redaction`) |
| `frontend` typecheck / build | covered by prior + Playwright webServer build |
| `npx playwright test e2e/control-plane.spec.ts` | **10 passed** (functional, mobile sizes, a11y) |

## Contract checks

- `execution_owner_count=1` (`DEMO_VALIDATION_SERVICE`)
- Stage3 execution capability forced false
- No synthetic zero fallback when Demo Execution unavailable
- Version labels separate: PR #6 head ≠ observation deployed SHA
- Federation write attempts only via explicit reject paths (405)
- Cost gate diagnosis analysis-only (`session_modification_forbidden=true`)

## Accessibility

- Control Plane page: axe serious/critical = 0 **without** global `disableRules`
- Status communicated via text + `data_status`, not color alone
- Mobile nav landmark `aria-label="主要導覽"`

## Bounded debt (nonblocking)

| rule | element | reason | owner | target_wave | blocking |
|------|---------|--------|-------|-------------|----------|
| (none recorded for control-plane page) | — | — | — | — | — |

Legacy Wave4 overview routes still use documented color-contrast disable in `accessibility.spec.ts` — **out of PR #23 Control Plane scope**; not applied to `/control-plane`.

## Freeze

`pr23_scope_frozen=true` after this report.  
`deploy=false` · `merge=false` · `live_effect=false`
