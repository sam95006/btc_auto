# PUB2-G Hard Bans (Customer Validation Concierge App)

Enforced by `tools/customer_validation/hard_bans.py` and
`backend/nexus_customer_validation_concierge/hard_bans.py`:

- no live public deployment / App Store / Play submission
- no live billing / real IAP / production customer database
- no custodial wallet / copy trading / automated customer trading
- no fabricated participants / interviews / paid pilots / metrics
- no merge of frozen PR #26 / #27 from this lane
- no exchange write / mainnet / real money / demo or shadow orders
- no private-core exposure from Concierge owned sources
- local/staging only

Initial required counters (must stay zero until genuine Founder enrollments):

- real_participant_count=0
- completed_interview_count=0
- paid_pilot_count=0
- plus all workflow step counters (consent, watchlist, WTP, objections, …)=0

THREE PASSES: `python tools/customer_validation_concierge/run_three_passes.py`
recomputes integrity digests three times and requires a match. Does not emit
`*_status.json` or `*_report.json`.
