# App Review demo mode

**Status:** ARCHITECTURE · allowed in `dev`/`staging` only · banned as default in `prod` flavor

## Purpose

Provide Apple/Google reviewers with a deterministic, explicitly labelled **DEMO PREVIEW** experience that does not fabricate live system health as real, and does not require production customer data.

## Activation

| Mechanism | Rule |
|-----------|------|
| Build flag `REVIEW_DEMO_ALLOWED` | true only for non-prod flavors |
| Runtime `NEXUS_PUBLIC_REVIEW_DEMO=1` | ignored if flavor forbids |
| Deep link `nexusdecision://review-demo?token=...` | token validated against public staging issuer |
| Reviewer credentials | synthetic accounts documented in `reviewer_notes_draft.md` |

## UX contract

- Persistent banner: `DEMO PREVIEW · NOT LIVE DATA · NOT INVESTMENT ADVICE`
- Every numeric widget must carry `source=demo_fixture` lineage
- LIVE mode components remain unavailable or show `Unavailable` rather than mixing demo into live claims
- No path to private-core routes
- Billing buttons show `Billing disabled` and do not call stores

## Data policy

- Fixtures are synthetic and labelled
- No fabricated paid pilots or fabricated interview evidence
- No profitability claims

## Exit

Leaving demo mode clears fixture caches and returns to honest Unavailable/Collecting states when live data is absent.
