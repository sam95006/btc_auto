# PUB2-I Public Product Analytics (North-Star Scaffolding)

Privacy-aware analytics scaffolding for the Public Decision Platform.

## North star

`CLOSED_DECISION_LOOPS_PER_ACTIVE_PAID_USER`

Scaffolding never fabricates a numeric north-star value. Empty cohorts report
`status=NO_OBSERVATIONS`, `value=null`, `count=0`.

## Metric schema

Canonical document:

`docs/product_analytics/NEXUS_PUBLIC_V2_PRODUCT_ANALYTICS_METRIC_SCHEMA_V1.json`

Covered product metrics:

- watchlist_activation
- first_decision_opened
- evidence_engagement
- counter_evidence_engagement
- task_success
- weekly_active_use
- decision_review_completion
- retention
- upgrade_intent
- customer_validation_conversion

## Privacy

- Default consent: denied (`product_analytics` purpose)
- Subject IDs: HMAC-SHA256 salted pseudonyms
- Forbidden props: email, phone, secrets, wallet, lesson/prompt text, etc.
- Local store only — no production customer database
- No live billing / IAP

## Hard bans

See `NEXUS_PUB2_I_HARD_BANS_V1.md`.

## Three passes

```bash
python backend/nexus_public_product_analytics/run_lane.py --write-schema
```

Does not emit `*_status.json`.
