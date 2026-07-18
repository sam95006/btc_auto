"""Market Intelligence research stores (Phase 4 Track B).

Read-only research persistence · no secrets · no trading coupling.
"""

from backend.market.intelligence.history_store import get_history_store
from backend.market.intelligence.outcome_store import get_outcome_store
from backend.market.intelligence.transition_store import get_transition_store

__all__ = ["get_history_store", "get_outcome_store", "get_transition_store"]
