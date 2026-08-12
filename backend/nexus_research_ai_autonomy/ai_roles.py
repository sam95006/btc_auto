"""Slow-path Quant / Reasoner / Critic — MUST NOT run inside fast-path hot loop."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class QuantResult:
    symbol: str
    score: float
    expected_move: float | None
    expected_edge: float | None
    estimated_cost: float | None
    side_bias: str  # LONG | SHORT | WAIT
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReasonerResult:
    symbol: str
    verdict: str  # LONG | SHORT | WAIT | BLOCK
    thesis: str
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    setup_type: str = ""
    entry_trigger: dict[str, Any] = field(default_factory=dict)
    entry_zone: dict[str, Any] = field(default_factory=dict)
    stop_logic: dict[str, Any] = field(default_factory=dict)
    take_profit_logic: dict[str, Any] = field(default_factory=dict)
    llm_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CriticResult:
    symbol: str
    verdict: str  # PASS | WATCH | REJECT
    objections: list[str] = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HotPathGuard:
    """Detects illegal AI/LLM invocation between trigger and order send."""

    def __init__(self) -> None:
        self.in_hot_path = False
        self.slow_path_leak_count = 0
        self.leaks: list[str] = []

    def begin_hot_path(self) -> None:
        self.in_hot_path = True

    def end_hot_path(self) -> None:
        self.in_hot_path = False

    def note_ai_call(self, name: str) -> None:
        if self.in_hot_path:
            self.slow_path_leak_count += 1
            self.leaks.append(name)


# Process-global guard used by reasoner/critic wrappers.
HOT_PATH_GUARD = HotPathGuard()


class DeepQuantEvaluator:
    """Deterministic deep quant on shortlisted symbols (capacity-aware)."""

    def evaluate(self, symbol: str, features: dict[str, Any], family: str) -> QuantResult:
        # Deterministic quant is allowed on slow path only by architecture;
        # invoking it inside the hot path is still a slow-path leak.
        if HOT_PATH_GUARD.in_hot_path:
            HOT_PATH_GUARD.note_ai_call("deep_quant_in_hot_path")
        f = dict(features or {})
        momentum = float(f.get("momentum") or 0.0)
        vol = float(f.get("volatility") or 0.5)
        spread = float(f.get("spread") or 0.0004)
        funding = float(f.get("funding") or 0.0)
        cost = max(spread * 2.0, 0.0003) + abs(funding) * 0.5
        expected_move = abs(momentum) * (0.01 + 0.02 * vol)
        edge = expected_move - cost
        if family in {"MEAN_REVERSION", "REVERSAL"}:
            side = "SHORT" if momentum > 0.2 else ("LONG" if momentum < -0.2 else "WAIT")
            edge = abs(momentum) * 0.008 - cost
        else:
            side = "LONG" if momentum > 0.15 else ("SHORT" if momentum < -0.15 else "WAIT")
        score = max(0.0, min(100.0, 50.0 + momentum * 40.0 + (10.0 if edge > 0 else -15.0)))
        notes = [f"family={family}", f"edge={edge:.6f}", f"cost={cost:.6f}"]
        return QuantResult(
            symbol=symbol,
            score=score,
            expected_move=expected_move,
            expected_edge=edge,
            estimated_cost=cost,
            side_bias=side,
            notes=notes,
        )


class ResearchReasoner:
    """Bounded reasoner — may be LLM-backed later; default deterministic."""

    def __init__(self, llm_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.llm_fn = llm_fn

    def reason(
        self,
        *,
        symbol: str,
        regime: str,
        family: str,
        quant: QuantResult,
        market: dict[str, Any] | None = None,
    ) -> ReasonerResult:
        HOT_PATH_GUARD.note_ai_call("reasoner")
        llm_used = False
        if self.llm_fn is not None:
            llm_used = True
            out = self.llm_fn(
                {
                    "symbol": symbol,
                    "regime": regime,
                    "family": family,
                    "quant": quant.to_dict(),
                    "market": market or {},
                }
            )
            return ReasonerResult(
                symbol=symbol,
                verdict=str(out.get("verdict") or "WAIT").upper(),
                thesis=str(out.get("thesis") or ""),
                confidence=float(out.get("confidence") or 0.0),
                supporting_evidence=list(out.get("supporting_evidence") or []),
                contradicting_evidence=list(out.get("contradicting_evidence") or []),
                setup_type=str(out.get("setup_type") or family),
                entry_trigger=dict(out.get("entry_trigger") or {}),
                entry_zone=dict(out.get("entry_zone") or {}),
                stop_logic=dict(out.get("stop_logic") or {}),
                take_profit_logic=dict(out.get("take_profit_logic") or {}),
                llm_used=True,
            )

        side = quant.side_bias
        if side == "WAIT" or quant.expected_edge is None or (quant.expected_edge or 0) <= 0:
            return ReasonerResult(
                symbol=symbol,
                verdict="WAIT",
                thesis="insufficient_edge_or_neutral_bias",
                confidence=0.35,
                supporting_evidence=list(quant.notes),
                contradicting_evidence=["edge_non_positive"],
                setup_type=family,
                llm_used=False,
            )

        px = float((market or {}).get("last_price") or (market or {}).get("price") or 0.0)
        atr_pct = float((market or {}).get("atr_pct") or 0.008)
        if side == "LONG":
            trigger_px = px * (1.0 + 0.001) if px else None
            stop_px = px * (1.0 - 1.5 * atr_pct) if px else None
            tp_px = px * (1.0 + 2.0 * atr_pct) if px else None
        else:
            trigger_px = px * (1.0 - 0.001) if px else None
            stop_px = px * (1.0 + 1.5 * atr_pct) if px else None
            tp_px = px * (1.0 - 2.0 * atr_pct) if px else None

        return ReasonerResult(
            symbol=symbol,
            verdict=side,
            thesis=f"{family} fits {regime} with quant edge {quant.expected_edge:.5f}",
            confidence=min(0.9, 0.45 + quant.score / 200.0),
            supporting_evidence=list(quant.notes) + [f"regime={regime}"],
            contradicting_evidence=[],
            setup_type=f"{family}_{side}",
            entry_trigger={"type": "price_cross", "price": trigger_px, "side": side},
            entry_zone={"mid": px, "width_pct": atr_pct},
            stop_logic={"type": "protective_stop", "price": stop_px, "atr_mult": 1.5},
            take_profit_logic={"type": "rr_target", "price": tp_px, "atr_mult": 2.0},
            llm_used=llm_used,
        )


class ResearchCritic:
    def __init__(self, llm_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.llm_fn = llm_fn

    def critique(self, reasoner: ReasonerResult, market: dict[str, Any] | None = None) -> CriticResult:
        HOT_PATH_GUARD.note_ai_call("critic")
        if self.llm_fn is not None:
            out = self.llm_fn({"reasoner": reasoner.to_dict(), "market": market or {}})
            return CriticResult(
                symbol=reasoner.symbol,
                verdict=str(out.get("verdict") or "WATCH").upper(),
                objections=list(out.get("objections") or []),
                llm_used=True,
            )

        objections: list[str] = []
        m = dict(market or {})
        funding = float(m.get("funding") or 0.0)
        if reasoner.verdict == "LONG" and funding > 0.0005:
            objections.append("funding_crowded_long")
        if reasoner.verdict == "SHORT" and funding < -0.0005:
            objections.append("funding_crowded_short")
        spread = float(m.get("spread") or 0.0)
        if spread > 0.002:
            objections.append("HARD:spread_extreme")
        if reasoner.confidence < 0.4 and reasoner.verdict in {"LONG", "SHORT"}:
            objections.append("low_confidence")

        if any(o.startswith("HARD:") for o in objections):
            verdict = "REJECT"
        elif objections:
            verdict = "WATCH"
        else:
            verdict = "PASS"
        return CriticResult(symbol=reasoner.symbol, verdict=verdict, objections=objections, llm_used=False)
