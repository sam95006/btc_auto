# V14-K Closed-Loop Scale V3

SIMULATED ONLY. CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING.

Targets: candidate_count>=50000, completed_lifecycle_count>=25000

50+ fixture symbols through validated InstrumentSpec universe.
Canonical path: Candidate → Decision → Risk → Simulated Intent → Simulated Order → Fill → Position → Exit → Reflection → Lesson Gate → Closure

Fault coverage: multi-symbol/regime, provider outage, partial fills, cancel-replace, clock anomaly, disk pressure, ledger interrupt, checkpoint rollback, Reflection/Lesson interrupt, kill switch, restart, qualification blocks.

No profitability calculation. No exchange writes. No auto-integrate.
