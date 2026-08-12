# V13-G Closed-Loop Scale V2

SIMULATED ONLY. CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING.

Targets: candidate_count>=10000, completed_lifecycle_count>=5000

Canonical path: Candidate → Decision → Risk → Simulated Intent → Simulated Order → Fill → Position → Exit → Reflection → Lesson Gate → Closure

Fault coverage: multi-symbol/regime, provider outage, partial fills, cancel-replace, clock rollback, disk pressure, ledger interrupt, checkpoint corruption, Reflection/Lesson interrupt, kill switch, restart, qualification blocks.

No profitability calculation. No exchange writes. No PR27 auto-integrate.
