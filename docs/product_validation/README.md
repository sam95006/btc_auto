# Concierge Validation Pack (PUB-I + PUB2-G)

Founder operations readiness for 10–20 genuine ICP participants, plus the
PUB2-G local/staging Concierge app.

## Tools

Python package: `tools/customer_validation/`
App package: `backend/nexus_customer_validation_concierge/`

| Tool | Module |
|---|---|
| Participant registry | `registry.py` |
| Consent | `consent.py` |
| Interview workflow | `interview.py` |
| Problem ranking | `problem_ranking.py` |
| Current workflow map | `workflow.py` |
| Watchlist onboarding | `watchlist_onboarding.py` |
| Decision Object Concierge delivery | `decision_object_concierge.py` |
| Weekly Founder review | `weekly_review.py` |
| Retention / WTP / objection / conversion evidence | `evidence.py` |
| Workflow spine + counters | `workflow_spine.py` |
| Hard bans + three-pass integrity | `hard_bans.py`, `integrity.py` |
| Local/staging Concierge app | `backend/nexus_customer_validation_concierge/` |

Local empty workspace: `tools/customer_validation/workspace/` (not a production customer database).

```bash
python tools/customer_validation_concierge/run_three_passes.py
python tools/customer_validation/run_ops.py
python -m backend.nexus_customer_validation_concierge.app
python -m pytest tests/test_pub2_g_customer_validation_concierge.py tests/test_customer_validation_operations.py -q
```

## Docs templates

- `NEXUS_PUB2_G_CONCIERGE_APP_V1.md`
- `NEXUS_PUB2_G_HARD_BANS_V1.md`
- `NEXUS_CONCIERGE_VALIDATION_OPERATIONS_V1.md`
- Screener, recruitment script, consent
- Daily / Decision / Thesis / Outcome templates
- Metrics tracker with pre-registered CONTINUE/ITERATE/PIVOT/KILL
- Weekly Founder review template

## Required initial counters

All remain `0` until real people participate:

- `real_participant_count=0`
- `completed_interview_count=0`
- `paid_pilot_count=0`
- consent / problem ranking / watchlist / Decision Object / weekly review /
  retention / WTP / objections / pilot conversion intent = 0

Do not fabricate participants, interviews, metrics, or paid pilots.
No `*_status.json` / `*_report.json` artifacts from this track.
