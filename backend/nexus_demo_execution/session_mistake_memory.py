"""Session-local mistake memory and decision deltas (no global strategy mutate)."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MistakeMemoryEntry:
    source_trade_case_id: str
    setup_key: str
    features: dict[str, Any]
    action: str
    created_at: float
    cooldown_until: float = 0.0
    score_penalty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_trade_case_id": self.source_trade_case_id,
            "setup_key": self.setup_key,
            "features": dict(self.features),
            "action": self.action,
            "created_at": self.created_at,
            "cooldown_until": self.cooldown_until,
            "score_penalty": self.score_penalty,
        }


@dataclass
class SessionMistakeMemory:
    entries: list[MistakeMemoryEntry] = field(default_factory=list)
    decision_deltas: list[dict[str, Any]] = field(default_factory=list)

    def remember_from_outcome(self, *, trade_case_id: str, candidate: dict[str, Any], outcome: str, cost_labels: list[str]) -> str:
        """Create bounded session-local guard from trade outcome features — not blanket symbol bans."""
        now = time.time()
        features = {
            "symbol": candidate.get("symbol"),
            "direction": candidate.get("direction"),
            "strategy": candidate.get("strategy"),
            "regime": candidate.get("regime"),
            "cost_labels": list(cost_labels),
            "outcome": outcome,
        }
        setup_key = "|".join(
            [
                str(features.get("symbol") or ""),
                str(features.get("direction") or ""),
                str(features.get("strategy") or ""),
                str(features.get("regime") or ""),
            ]
        )
        action = "NO_CHANGE_JUSTIFIED"
        cooldown = 0.0
        penalty = 0.0
        if "fee_churn_candidate" in cost_labels or "BLOCK_COST_DOMINATED_ENTRY" in cost_labels or "gross_edge_insufficient" in cost_labels:
            action = "BLOCK_COST_DOMINATED_SETUP"
            cooldown = now + 45 * 60
            penalty = 0.35
        elif outcome == "BAD_PROCESS_LOSS" or outcome == "BAD_PROCESS_WIN":
            action = "BLOCK_REPEATED_BAD_PROCESS"
            cooldown = now + 60 * 60
            penalty = 0.5
        elif outcome == "GOOD_PROCESS_LOSS" and "direction_correct_but_net_loss" in cost_labels:
            action = "REQUIRE_EXTRA_CONFIRMATION"
            cooldown = now + 30 * 60
            penalty = 0.2
        elif outcome in {"GOOD_PROCESS_LOSS", "GOOD_PROCESS_WIN"}:
            action = "SIMILAR_CASE_SCORE_PENALTY"
            penalty = 0.1
            cooldown = now + 20 * 60

        entry = MistakeMemoryEntry(
            source_trade_case_id=trade_case_id,
            setup_key=setup_key,
            features=features,
            action=action,
            created_at=now,
            cooldown_until=cooldown,
            score_penalty=penalty,
        )
        self.entries.append(entry)
        return action

    def apply(
        self,
        *,
        candidate: dict[str, Any],
        before_score: float,
        before_verdict: str = "ALLOW",
    ) -> dict[str, Any]:
        now = time.time()
        setup_key = "|".join(
            [
                str(candidate.get("symbol") or ""),
                str(candidate.get("direction") or ""),
                str(candidate.get("strategy") or ""),
                str(candidate.get("regime") or ""),
            ]
        )
        after_score = before_score
        after_verdict = before_verdict
        guard_action = "NO_CHANGE_JUSTIFIED"
        source = ""
        for entry in reversed(self.entries):
            # Feature-overlap similarity (not blanket symbol ban)
            same_setup = entry.setup_key == setup_key
            cost_overlap = bool(
                set(entry.features.get("cost_labels") or [])
                & {"fee_churn_candidate", "gross_edge_insufficient", "BLOCK_COST_DOMINATED_ENTRY"}
            )
            similar = same_setup or (
                entry.features.get("strategy") == candidate.get("strategy")
                and entry.features.get("regime") == candidate.get("regime")
                and cost_overlap
            )
            if not similar:
                continue
            source = entry.source_trade_case_id
            guard_action = entry.action
            after_score = max(0.0, after_score - entry.score_penalty)
            if entry.action in {"BLOCK_COST_DOMINATED_SETUP", "BLOCK_REPEATED_BAD_PROCESS", "EXACT_SETUP_COOLDOWN"}:
                if now < entry.cooldown_until or entry.action.startswith("BLOCK_"):
                    after_verdict = "BLOCK"
                    if entry.action == "BLOCK_COST_DOMINATED_SETUP":
                        guard_action = "BLOCK_COST_DOMINATED_SETUP"
                    elif entry.action == "BLOCK_REPEATED_BAD_PROCESS":
                        guard_action = "BLOCK_REPEATED_BAD_PROCESS"
                    else:
                        guard_action = "EXACT_SETUP_COOLDOWN"
                    break
            if entry.action == "REQUIRE_EXTRA_CONFIRMATION":
                # Require stronger score
                if after_score < before_score * 0.9 + 0.15:
                    after_verdict = "BLOCK"
                    guard_action = "REQUIRE_EXTRA_CONFIRMATION"
                    break
            if entry.action == "SIMILAR_CASE_SCORE_PENALTY":
                guard_action = "SIMILAR_CASE_SCORE_PENALTY"
                break

        delta = {
            "delta_id": f"delta-{uuid.uuid4().hex[:10]}",
            "source_trade_case_id": source,
            "similar_candidate_id": candidate.get("candidate_id"),
            "similarity_score": 1.0 if setup_key and source else 0.0,
            "before_verdict": before_verdict,
            "after_verdict": after_verdict,
            "before_score": before_score,
            "after_score": after_score,
            "guard_action": guard_action,
            "evidence_refs": [source] if source else [],
            "observed_at": now,
        }
        self.decision_deltas.append(delta)
        return delta

    def summary(self) -> dict[str, Any]:
        return {
            "entry_count": len(self.entries),
            "decision_delta_count": len(self.decision_deltas),
            "actions": [e.action for e in self.entries],
        }
