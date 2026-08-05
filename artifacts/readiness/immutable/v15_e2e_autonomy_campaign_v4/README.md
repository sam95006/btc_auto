# V15-K End-to-End Autonomy Campaign V4

SIMULATED ONLY. CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING.

Targets: candidate_count>=100000, completed_lifecycle_count>=50000

100+ fixture symbols through validated InstrumentSpec universe.
Canonical path: Candidate → Decision → Risk → Simulated Intent → Simulated Order → Fill → Position → Exit → Reflection → Lesson Gate → Closure

Fault coverage: multi-symbol/regime, provider outage, capture degradation, partial fills, cancel-replace, clock anomaly, disk pressure, ledger interrupt, snapshot corruption, checkpoint rollback, Reflection/Lesson interrupt, kill switch, restart, qualification blocks.

No profitability calculation. No exchange writes. No auto-integrate.
No *_status.json (Coordinator final message only).
