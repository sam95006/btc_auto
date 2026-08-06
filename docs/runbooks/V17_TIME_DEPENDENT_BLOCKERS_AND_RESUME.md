# V17 Time-Dependent Blockers and Resume Commands

**Status: NOT COMPLETE — blockers remain honest.**

This runbook documents resume commands and preflight contracts for work that
**must not** be claimed finished in the V17 deep-engineering wave. Fixture
tests and contracts may exist; wall-clock / platform / Founder-gated outcomes
do not.

Do **not** mark any item below as PASS/COMPLETE from this document alone.

## Hard rule

Allowed now:

- resume command documentation
- preflight checks
- contracts
- fixture tests
- explicit `blocked_reason`

Forbidden:

- claiming 14d capture completion
- claiming formal Walk-Forward / untouched OOS
- claiming real Lesson Prevention
- claiming V2.3 provider completion
- claiming real customer interviews / paid pilots
- claiming signed iOS / store review
- claiming production billing / mainnet / real money

## Blocked inventory

| Item | State | Blocked reason | Resume command (do not claim success) |
| --- | --- | --- | --- |
| 14d capture completion | BLOCKED | Wall-clock UTC qualification window not sealed | `python tools/research/ms_accum_v13_integrity_14d_preflight.py` (preflight only) |
| Real Event Study | BLOCKED | Requires sealed capture + authorized research window | Preflight against research registry; no silent synthetic fill |
| Formal Walk-Forward | BLOCKED | Founder ban this round | Do not run WF; keep compiler/split fixtures only |
| Untouched OOS | BLOCKED | Founder ban this round | Do not consume OOS; contamination guards only |
| Real Lesson Prevention | BLOCKED | V2.3 incomplete | Lesson Gate contracts/fixtures only |
| V2.3 provider completion | BLOCKED | Provider capacity / authorization | Provider health probe only; no fake Live |
| Real customer interviews | BLOCKED | No fabricated participants | Concierge workflow prep only |
| Paid pilot | BLOCKED | No production billing | Display-only entitlements |
| 30–90 day unattended validation | BLOCKED | Wall-clock | Keep SLO contracts; do not claim endurance PASS |
| iOS signed build | PLATFORM_BLOCKED | Windows host without macOS/Xcode | Flutter iOS config check only |
| Store review | BLOCKED | No App Store / Play submission | Compliance drafts only |
| Production billing | BLOCKED | `LIVE_BILLING_ENABLED=false` | Keep billing provider = NONE |
| Real exchange execution / mainnet / real money | BLOCKED | Hard ban | Exchange write capability must remain 0 |

## Public / Mobile honesty reminders

- Unbound Live domains must surface as `PROVIDER_REQUIRED` (never fabricated numbers).
- Stale cache must show an explicit stale indicator.
- Unavailable must never render as `0`.
- Member execution / trade / copy / exchange controls must remain count `0` on web and mobile.

## Resume checklist (when Founder unblocks)

1. Confirm Founder usage / On-Demand gates allow new work.
2. Re-run the item-specific preflight (not the full claim).
3. Record machine evidence under `D:\NEXUS_RUNTIME\evidence_coordinator\`.
4. Update only the canonical report via Coordinator — never from this lane.
5. Leave `status` as `BLOCKED` / `PLATFORM_BLOCKED` until real evidence lands.

## Related parity artifact

Frozen public↔mobile field contract:

`artifacts/readiness/immutable/pub17_public_mobile_parity/public_mobile_parity_contract.json`

Gate:

```bash
python tools/public/run_pub17_public_mobile_parity_gate.py
```
