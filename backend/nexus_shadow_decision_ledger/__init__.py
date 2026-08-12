"""V18-F Shadow Decision Ledger and Learning Bridge.

Shadow Decision ≠ Shadow Order ≠ exchange orders.
SHADOW_OPENED = internal virtual research position ONLY.
Public invariants: actual_ordered=false, actual_filled=false, exchange_order_id=null.
Learning bridge emits Lesson CANDIDATE only — never ACTIVE.
"""
from __future__ import annotations

from backend.nexus_shadow_decision_ledger.constants import (
    HARD_BANS,
    LIFECYCLE_STATES,
    SCHEMA,
)
from backend.nexus_shadow_decision_ledger.contracts import (
    ShadowDecisionRecord,
    build_empty_record,
)
from backend.nexus_shadow_decision_ledger.ledger import ShadowDecisionLedger
from backend.nexus_shadow_decision_ledger.learning_bridge import ShadowLearningBridge
from backend.nexus_shadow_decision_ledger.lifecycle import ShadowDecisionLifecycle

__all__ = [
    "HARD_BANS",
    "LIFECYCLE_STATES",
    "SCHEMA",
    "ShadowDecisionLedger",
    "ShadowDecisionLifecycle",
    "ShadowDecisionRecord",
    "ShadowLearningBridge",
    "build_empty_record",
]
