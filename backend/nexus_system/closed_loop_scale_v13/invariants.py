"""Required zero-invariants and hard bans for V13-G closed-loop scale."""
from __future__ import annotations

from typing import Any

REQUIRED_ZERO_INVARIANTS: tuple[str, ...] = (
    "duplicate_decision_count",
    "duplicate_intent_count",
    "duplicate_position_count",
    "orphan_lifecycle_count",
    "unclosed_intent_count",
    "untracked_fill_count",
    "cost_bridge_failure_count",
    "risk_limit_bypass_count",
    "evidence_binding_failure_count",
    "checkpoint_loss_count",
    "exchange_write_attempt_count",
)

HARD_BANS: tuple[str, ...] = (
    "no_profitability_calculation",
    "no_demo_shadow_mainnet_real_money",
    "no_exchange_write",
    "no_formal_walkforward_oos",
    "no_auto_integrate_pr27",
    "no_decorative_intent_position_ids",
    "no_g_deletion",
)


def empty_invariant_counts() -> dict[str, int]:
    return {k: 0 for k in REQUIRED_ZERO_INVARIANTS}


def merge_invariant_counts(*sources: dict[str, Any]) -> dict[str, int]:
    out = empty_invariant_counts()
    for src in sources:
        for k in REQUIRED_ZERO_INVARIANTS:
            out[k] += int((src or {}).get(k, 0) or 0)
    return out


def invariants_pass(counts: dict[str, Any]) -> bool:
    return all(int((counts or {}).get(k, 0) or 0) == 0 for k in REQUIRED_ZERO_INVARIANTS)


def violations(counts: dict[str, Any]) -> dict[str, int]:
    return {
        k: int((counts or {}).get(k, 0) or 0)
        for k in REQUIRED_ZERO_INVARIANTS
        if int((counts or {}).get(k, 0) or 0) != 0
    }


__all__ = [
    "HARD_BANS",
    "REQUIRED_ZERO_INVARIANTS",
    "empty_invariant_counts",
    "invariants_pass",
    "merge_invariant_counts",
    "violations",
]
