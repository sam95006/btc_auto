# PUB2-I Hard Bans (Product Analytics)

Enforced by `backend/nexus_public_product_analytics/hard_bans.py`:

- no live public deployment / App Store / Play submission
- no live billing / real IAP / production customer database
- no custodial wallet / copy trading / automated customer trading
- no fabricated metrics / WAU / conversion rates / participants
- no tracking without `product_analytics` consent
- no PII in analytics properties
- no merge of frozen PR #26 / #27 from this lane
- no exchange write / mainnet / real money / demo or shadow orders
- no private-core exposure
- no human-facing `*_status.json` emission

Initial observation policy (must remain honest until real consented events exist):

- north_star value = null / NO_OBSERVATIONS
- metric counts = 0 when no events
- fabricated_results_forbidden = true

THREE PASSES: `python backend/nexus_public_product_analytics/run_lane.py --write-schema`
