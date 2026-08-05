# V11 Runtime Durability + DR V2

Full scale capability: 1_000_000 ledger events, 1_000 snapshots, 100 recovery drills.
Configure via `NEXUS_DURABILITY_V2_MODE=full|evidence|smoke` or explicit count env vars.

Hard rules: no silent recovery guess; ambiguous states block; no exchange write.
