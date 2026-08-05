# NEXUS PUB2-G Customer Validation Concierge App

Usable **local/staging** Founder workflow for real Concierge validation
participants. Does not fabricate results.

## Workflow spine

1. consent
2. interview
3. problem ranking
4. watchlist onboarding
5. Decision Object delivery
6. weekly review
7. retention
8. willingness to pay
9. objections
10. pilot conversion

## Run locally

```bash
# Empty workspace + three-pass integrity (stdout + proof JSON, never *_status.json)
python tools/customer_validation_concierge/run_three_passes.py

# Standalone Concierge app (127.0.0.1 only)
python -m backend.nexus_customer_validation_concierge.app
# UI:  http://127.0.0.1:8765/concierge-validation
# API: http://127.0.0.1:8765/api/public/v2/concierge-validation/meta

python -m pytest tests/test_pub2_g_customer_validation_concierge.py tests/test_customer_validation_operations.py -q
```

When mounted via `run.py`, the same routes are available under the main Flask app.

## Counters

All counters start at **0** and stay at 0 until real people participate.
Package workspace under `tools/customer_validation/workspace/` ships empty.

## Hard bans

See `NEXUS_PUB2_G_HARD_BANS_V1.md`.
