# PUB-I Hard Bans (Customer Validation Operations)

Public + fabrication bans enforced by `tools/customer_validation/hard_bans.py`:

- no live public deployment / App Store / Play submission
- no live billing / real IAP / production customer database
- no custodial wallet / copy trading / automated customer trading
- no fabricated participants / interviews / paid pilots
- no merge of frozen PR #26 / #27 from this lane
- no exchange write / mainnet / real money / demo or shadow orders

Initial required counters (must stay zero until genuine Founder enrollments):

- real_participant_count=0
- completed_interview_count=0
- paid_pilot_count=0

TWO PASSES: `python tools/customer_validation/run_ops.py` recomputes integrity digests twice and requires a match. Does not emit `*_status.json`.
