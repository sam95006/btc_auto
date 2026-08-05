"""Real ledger guard — counterfactuals never rewrite observed trades."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from backend.nexus_counterfactual_replay_v16.hard_bans import HardBanViolation, refuse_rewrite_real_ledger
from backend.nexus_counterfactual_replay_v16.types import DecisionTrade


def ledger_fingerprint(decision: DecisionTrade) -> str:
    payload = {
        "decision_id": decision.decision_id,
        "trade_id": decision.trade_id,
        "symbol": decision.symbol,
        "side": decision.side,
        "entry_ts_ms": decision.entry_ts_ms,
        "exit_ts_ms": decision.exit_ts_ms,
        "entry_price": decision.entry_price,
        "exit_price": decision.exit_price,
        "stop_price": decision.stop_price,
        "take_profit_price": decision.take_profit_price,
        "size": decision.size,
        "strategy_expert": decision.strategy_expert,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def freeze_ledger_snapshot(decision: DecisionTrade) -> dict[str, Any]:
    """Immutable copy of the real/observed decision — read-only for CF replay."""
    snap = decision.to_dict()
    snap["ledger_fingerprint"] = decision.ledger_fingerprint or ledger_fingerprint(decision)
    snap["mutable"] = False
    snap["counterfactual_may_rewrite"] = False
    return copy.deepcopy(snap)


def assert_ledger_unchanged(
    original: DecisionTrade | dict[str, Any],
    candidate: DecisionTrade | dict[str, Any],
) -> None:
    """Hard ban: CF engine must not mutate the real ledger record."""
    o = original.to_dict() if isinstance(original, DecisionTrade) else dict(original)
    c = candidate.to_dict() if isinstance(candidate, DecisionTrade) else dict(candidate)
    keys = (
        "decision_id",
        "trade_id",
        "symbol",
        "side",
        "entry_ts_ms",
        "exit_ts_ms",
        "entry_price",
        "exit_price",
        "stop_price",
        "take_profit_price",
        "size",
        "strategy_expert",
    )
    for k in keys:
        if o.get(k) != c.get(k):
            refuse_rewrite_real_ledger()
    ofp = o.get("ledger_fingerprint") or ledger_fingerprint(
        DecisionTrade(**{**{kk: o[kk] for kk in keys}, **{
            "decision_ts_ms": o.get("decision_ts_ms", o.get("entry_ts_ms")),
            "data_trust_at_decision": o.get("data_trust_at_decision", 1.0),
            "regime_at_decision": o.get("regime_at_decision", "UNKNOWN"),
        }})
    )
    cfp = c.get("ledger_fingerprint")
    if cfp and cfp != ofp:
        raise HardBanViolation(f"no_rewrite_real_ledger:fingerprint_mismatch:{ofp[:12]}")


def assert_outcome_not_real_performance(outcome: dict[str, Any]) -> None:
    if outcome.get("is_real_performance") is True:
        raise HardBanViolation("no_counterfactual_profit_as_real_performance")
    if outcome.get("is_counterfactual") is False and outcome.get("path_id") not in {
        "observed_baseline",
        "baseline_observed",
    }:
        raise HardBanViolation("no_counterfactual_profit_as_real_performance:missing_cf_flag")
