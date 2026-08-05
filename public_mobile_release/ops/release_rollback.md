# Release rollback — public mobile

**Status:** RUNBOOK_DRAFT · NON_SUBMISSION

## Principles

1. Prefer **feature-flag kill switches** over rushed store resubmits.
2. Prefer **staged rollout halt** over production track promotion (promotion banned here).
3. Binary rollback uses prior artifact from CI retention — not G-source.

## Rollback matrix

| Layer | Action |
|-------|--------|
| Remote config / regional flags | Set `membership_signup=false` or disable broken feature |
| API gateway | Route traffic to last-known-good public gateway revision |
| Mobile binary | Halt rollout; publish prior build only when store ops authorized outside PUB-L |
| Entitlements | Freeze verify endpoint (`BILLING_DISABLED`) |
| Deletion | Pause PURGING worker; keep PENDING queue durable |

## CI guards

- `publish_to_stores` must be false
- Rollback jobs must not invoke store-delivery actions listed in `FORBIDDEN_ROLLBACK_ACTIONS`
- Artifacts retained 14 days per signing policy

## Verification after rollback

- Hard-ban gate green
- Review demo still labelled
- No private-field leakage regressions
- Deletion endpoints still reachable or explicitly status-paged
