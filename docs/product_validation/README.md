# Concierge Validation Pack (PUB-I)

Founder operations readiness for 10–20 genuine ICP participants.

## Tools

Python package: `tools/customer_validation/`

| Tool | Module |
|---|---|
| Participant registry | `registry.py` |
| Consent | `consent.py` |
| Interview workflow | `interview.py` |
| Problem ranking | `problem_ranking.py` |
| Current workflow map | `workflow.py` |
| Decision Object Concierge delivery | `decision_object_concierge.py` |
| Weekly Founder review | `weekly_review.py` |
| Retention / WTP / objection / conversion evidence | `evidence.py` |
| Hard bans + two-pass integrity | `hard_bans.py`, `integrity.py` |

Local empty workspace: `tools/customer_validation/workspace/` (not a production customer database).

```bash
python tools/customer_validation/run_ops.py
python -m pytest tests/test_customer_validation_operations.py -q
```

## Docs templates

- `NEXUS_CONCIERGE_VALIDATION_OPERATIONS_V1.md`
- Screener, recruitment script, consent
- Daily / Decision / Thesis / Outcome templates
- Metrics tracker with pre-registered CONTINUE/ITERATE/PIVOT/KILL
- Weekly Founder review template

## Required initial counters

- `real_participant_count=0`
- `completed_interview_count=0`
- `paid_pilot_count=0`

Do not fabricate participants, interviews, or paid pilots.
No `*_status.json` artifacts from this track.
