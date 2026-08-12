# V12-D Disaster Recovery Control

Proves cold/warm restart, LKG/checkpoint restore, ledger-tail reconciliation,
ambiguous-state blocking, kill switch after recovery, and storage migration recovery.

Hard bans: no Demo / exchange write / mainnet; no PR27 merge; no silent recovery guesses.
Builds on V11.1 durability: false LKG banned, checksummed ledger position, owner-only duplicate intent.
