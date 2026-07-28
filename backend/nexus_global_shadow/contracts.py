"""Global market six-role shadow contracts (no fleet_id)."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_global_shadow import SCHEMA_VERSION


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def forbid_mode(mode: str) -> None:
    if mode in {"DEMO_WRITE", "MAINNET", "REAL_MONEY", "LIVE_EXECUTION"}:
        raise ValueError(f"forbidden_mode:{mode}")


class Mode(str, Enum):
    SHADOW = "SHADOW"
    REPLAY = "REPLAY"
    FIXTURE = "FIXTURE"
    PAPER = "PAPER"


class Regime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"
    EVENT_RISK = "EVENT_RISK"
    UNCERTAIN = "UNCERTAIN"


class RoleName(str, Enum):
    MARKET_CONTEXT = "Market Context"
    MARKET_STRUCTURE = "Market Structure"
    RISK_CRITIC = "Risk Critic"
    PORTFOLIO_MANAGER = "Portfolio Manager"
    PERFORMANCE_ANALYST = "Performance Analyst"
    REFLECTION_ANALYST = "Reflection Analyst"


class RoleVerdict(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"


class LifecycleState(str, Enum):
    CANDIDATE = "CANDIDATE"
    SIX_ROLE_REVIEWED = "SIX_ROLE_REVIEWED"
    RISK_APPROVED = "RISK_APPROVED"
    PORTFOLIO_SELECTED = "PORTFOLIO_SELECTED"
    SHADOW_OPEN_PENDING = "SHADOW_OPEN_PENDING"
    SHADOW_OPEN = "SHADOW_OPEN"
    PROTECTED_SIMULATED = "PROTECTED_SIMULATED"
    EXIT_PENDING = "EXIT_PENDING"
    SHADOW_CLOSED = "SHADOW_CLOSED"
    OUTCOME_CREATED = "OUTCOME_CREATED"
    REFLECTION_CREATED = "REFLECTION_CREATED"
    PATCH_PROPOSED = "PATCH_PROPOSED"
    REPLAY_VALIDATED = "REPLAY_VALIDATED"
    OOS_VALIDATED = "OOS_VALIDATED"
    SHADOW_APPLIED = "SHADOW_APPLIED"
    ARCHIVED = "ARCHIVED"


LEGAL_TRANSITIONS = {
    LifecycleState.CANDIDATE: {LifecycleState.SIX_ROLE_REVIEWED, LifecycleState.ARCHIVED},
    LifecycleState.SIX_ROLE_REVIEWED: {LifecycleState.RISK_APPROVED, LifecycleState.ARCHIVED},
    LifecycleState.RISK_APPROVED: {LifecycleState.PORTFOLIO_SELECTED, LifecycleState.ARCHIVED},
    LifecycleState.PORTFOLIO_SELECTED: {LifecycleState.SHADOW_OPEN_PENDING, LifecycleState.ARCHIVED},
    LifecycleState.SHADOW_OPEN_PENDING: {LifecycleState.SHADOW_OPEN, LifecycleState.ARCHIVED},
    LifecycleState.SHADOW_OPEN: {LifecycleState.PROTECTED_SIMULATED, LifecycleState.EXIT_PENDING},
    LifecycleState.PROTECTED_SIMULATED: {LifecycleState.EXIT_PENDING},
    LifecycleState.EXIT_PENDING: {LifecycleState.SHADOW_CLOSED},
    LifecycleState.SHADOW_CLOSED: {LifecycleState.OUTCOME_CREATED},
    LifecycleState.OUTCOME_CREATED: {LifecycleState.REFLECTION_CREATED},
    LifecycleState.REFLECTION_CREATED: {LifecycleState.PATCH_PROPOSED, LifecycleState.ARCHIVED},
    LifecycleState.PATCH_PROPOSED: {LifecycleState.REPLAY_VALIDATED, LifecycleState.ARCHIVED},
    LifecycleState.REPLAY_VALIDATED: {LifecycleState.OOS_VALIDATED, LifecycleState.ARCHIVED},
    LifecycleState.OOS_VALIDATED: {LifecycleState.SHADOW_APPLIED, LifecycleState.ARCHIVED},
    LifecycleState.SHADOW_APPLIED: {LifecycleState.ARCHIVED},
    LifecycleState.ARCHIVED: set(),
}


@dataclass
class EvidenceEnvelope:
    schema_version: str = SCHEMA_VERSION
    record_id: str = field(default_factory=lambda: new_id("ev"))
    correlation_id: str = ""
    session_id: str = ""
    universe_snapshot_id: str = ""
    instrument_id: str = ""
    symbol: str = ""
    mode: str = Mode.SHADOW.value
    source: str = "wave2_global"
    provider: str = "bybit"
    observed_at: int = field(default_factory=now_ms)
    captured_at: int = field(default_factory=now_ms)
    created_at: int = field(default_factory=now_ms)
    freshness: str = "UNKNOWN"
    quality: str = "UNKNOWN"
    completeness: str = "UNKNOWN"
    missing_fields: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    code_sha: str = ""
    policy_version: str = "v1"
    model_version: str = "v1"
    dataset_hash: str = ""
    sequence_number: int = 0
    boot_id: str = ""
    commit_sha: str = ""
    checksum: str = ""

    def finalize(self) -> "EvidenceEnvelope":
        forbid_mode(self.mode)
        payload = {
            "record_id": self.record_id,
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "universe_snapshot_id": self.universe_snapshot_id,
            "symbol": self.symbol,
            "mode": self.mode,
            "observed_at": self.observed_at,
            "sequence_number": self.sequence_number,
        }
        self.checksum = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:32]
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketInstrument(EvidenceEnvelope):
    base_coin: str = ""
    quote_coin: str = "USDT"
    contract_type: str = "LinearPerpetual"
    status: str = "Trading"
    launch_time: int | None = None
    tick_size: float | None = None
    qty_step: float | None = None
    min_order_qty: float | None = None
    min_notional: float | None = None
    max_leverage_available: float | None = None


@dataclass
class MarketQualitySnapshot(EvidenceEnvelope):
    volume_24h: float | None = None
    turnover_24h: float | None = None
    trade_count: int | None = None
    spread_bps: float | None = None
    bid_depth: float | None = None
    ask_depth: float | None = None
    depth_imbalance: float | None = None
    estimated_slippage: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    price_freshness: str = "UNKNOWN"
    orderbook_freshness: str = "UNKNOWN"
    provider_quality: str = "UNKNOWN"
    data_completeness: str = "UNKNOWN"
    liquidity_tier: str = "UNKNOWN"
    risk_tier: str = "UNKNOWN"
    anomaly_flags: list[str] = field(default_factory=list)


@dataclass
class UniverseEligibility(EvidenceEnvelope):
    eligible: bool = False
    verdict: str = "FAIL"
    supporting_evidence: list[str] = field(default_factory=list)
    exclusion_reasons: list[str] = field(default_factory=list)
    evaluated_at: int = field(default_factory=now_ms)


@dataclass
class UniverseSnapshot(EvidenceEnvelope):
    total_markets: int = 0
    usdt_perpetual_markets: int = 0
    trading_markets: int = 0
    fresh_markets: int = 0
    quality_pass_markets: int = 0
    eligible_markets: int = 0
    excluded_markets: int = 0
    exclusion_reason_counts: dict[str, int] = field(default_factory=dict)
    instruments: list[dict[str, Any]] = field(default_factory=list)
    provider_status: str = "OK"
    degraded: bool = False


@dataclass
class MarketObservation(EvidenceEnvelope):
    last_price: float | None = None
    mark_price: float | None = None
    volume_24h: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    spread_bps: float | None = None
    liquidity_score: float | None = None
    volatility: float | None = None
    momentum: float | None = None


@dataclass
class MarketRegime(EvidenceEnvelope):
    regime: str = Regime.UNCERTAIN.value
    confidence: float | None = None
    confidence_calibration: str = "UNCALIBRATED"
    supporting_factors: list[str] = field(default_factory=list)
    contradicting_factors: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    data_quality: str = "UNKNOWN"
    transition_from: str | None = None
    transition_reason: str | None = None
    fallback_reason: str | None = None


@dataclass
class StrategyContext(EvidenceEnvelope):
    strategy_id: str = ""
    strategy_fit: float | None = None
    strategy_status: str = "BLOCKED"
    entry_prerequisites: list[str] = field(default_factory=list)
    invalidation: str = ""
    required_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)


@dataclass
class IntelligenceSnapshot(EvidenceEnvelope):
    price_structure: str | None = None
    momentum: float | None = None
    volatility: float | None = None
    volume: float | None = None
    liquidity: float | None = None
    spread: float | None = None
    depth: float | None = None
    orderbook_imbalance: float | None = None
    funding: float | None = None
    open_interest: float | None = None
    liquidation_context: str = "MISSING"
    long_short_ratio: float | None = None
    market_quality: str = "UNKNOWN"
    cross_market_context: dict[str, Any] = field(default_factory=dict)
    benchmark_context: dict[str, Any] = field(default_factory=dict)
    market_breadth: dict[str, Any] = field(default_factory=dict)
    news_context_availability: str = "UNAVAILABLE"
    event_risk: str = "UNKNOWN"
    provider_quality: str = "UNKNOWN"
    data_anomalies: list[str] = field(default_factory=list)
    regime: str = Regime.UNCERTAIN.value
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate(EvidenceEnvelope):
    candidate_id: str = field(default_factory=lambda: new_id("cand"))
    direction: str = "NEUTRAL"
    strategy_id: str = ""
    regime: str = Regime.UNCERTAIN.value
    entry_thesis: str = ""
    entry_condition: str = ""
    invalidation: str = ""
    expected_horizon: int | None = None
    candidate_expiry: int | None = None
    confidence: float | None = None
    confidence_calibration: str = "UNCALIBRATED"
    quality_score: float | None = None
    risk_score: float | None = None
    regime_fit: float | None = None
    strategy_fit: float | None = None
    liquidity_fit: float | None = None
    spread: float | None = None
    estimated_slippage: float | None = None
    funding_context: float | None = None
    open_interest_context: float | None = None
    evidence_quality: str = "UNKNOWN"
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)
    expires_at: int | None = None
    status: str = "WATCHING"
    rank_score: float | None = None
    ranking_version: str = "v1"
    score_components: dict[str, float] = field(default_factory=dict)
    score_waterfall: list[str] = field(default_factory=list)
    rank: int | None = None


@dataclass
class RoleReview(EvidenceEnvelope):
    role: str = ""
    candidate_id: str = ""
    verdict: str = RoleVerdict.UNKNOWN.value
    score: float | None = None
    confidence: float | None = None
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)
    prompt_version: str = "v1"
    reviewed_at: int = field(default_factory=now_ms)
    trace_id: str = field(default_factory=lambda: new_id("trace"))


@dataclass
class SixRoleReviewSet(EvidenceEnvelope):
    candidate_id: str = ""
    reviews: list[dict[str, Any]] = field(default_factory=list)
    review_complete: bool = False
    pass_count: int = 0
    watch_count: int = 0
    block_count: int = 0
    unknown_count: int = 0
    consensus: str = "UNKNOWN"
    risk_critic_verdict: str = RoleVerdict.UNKNOWN.value
    mandatory_veto: bool = True
    contradictions: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    review_evidence_refs: list[str] = field(default_factory=list)


@dataclass
class RiskCriticVerdict(EvidenceEnvelope):
    candidate_id: str = ""
    verdict: str = RoleVerdict.UNKNOWN.value
    mandatory_veto: bool = True
    reasons: list[str] = field(default_factory=list)


@dataclass
class PortfolioVerdict(EvidenceEnvelope):
    candidate_id: str = ""
    selected: bool = False
    portfolio_rank: int | None = None
    risk_before: float | None = None
    risk_after: float | None = None
    marginal_contribution: float | None = None
    correlation_group: str | None = None
    direction_exposure: dict[str, int] = field(default_factory=dict)
    strategy_exposure: dict[str, int] = field(default_factory=dict)
    cluster_exposure: dict[str, int] = field(default_factory=dict)
    block_reasons: list[str] = field(default_factory=list)
    evaluated_at: int = field(default_factory=now_ms)
    open_positions: int = 0
    pending_intents: int = 0
    selected_ids: list[str] = field(default_factory=list)


@dataclass
class ShadowPosition(EvidenceEnvelope):
    position_id: str = field(default_factory=lambda: new_id("spos"))
    candidate_id: str = ""
    direction: str = "LONG"
    strategy_id: str = ""
    regime: str = ""
    state: str = LifecycleState.CANDIDATE.value
    entry_time: int | None = None
    entry_price: float | None = None
    simulated_fee: float | None = None
    simulated_slippage: float | None = None
    position_size: float | None = None
    risk_budget: float | None = None
    portfolio_risk_at_open: float | None = None
    correlation_group: str | None = None
    protection_plan: dict[str, Any] = field(default_factory=dict)
    exit_policy: dict[str, Any] = field(default_factory=dict)
    max_hold: int | None = None
    invalidation: str | None = None
    mark_series: list[float] = field(default_factory=list)
    exit_reason: str | None = None
    exit_time: int | None = None
    exit_price: float | None = None
    gross_pnl: float | None = None
    fees: float | None = None
    funding: float | None = None
    slippage: float | None = None
    net_pnl: float | None = None
    r_multiple: float | None = None
    data_completeness: str = "UNKNOWN"


@dataclass
class Outcome(EvidenceEnvelope):
    position_id: str = ""
    exit_reason: str | None = None
    gross_pnl: float | None = None
    fees: float | None = None
    funding: float | None = None
    slippage: float | None = None
    net_pnl: float | None = None
    r_multiple: float | None = None
    incomplete: bool = True


@dataclass
class Reflection(EvidenceEnvelope):
    outcome_id: str = ""
    what_happened: str = ""
    what_was_expected: str = ""
    what_differed: str = ""
    data_quality_issue: str | None = None
    regime_mismatch: str | None = None
    strategy_mismatch: str | None = None
    entry_issue: str | None = None
    exit_issue: str | None = None
    risk_issue: str | None = None
    portfolio_issue: str | None = None
    execution_simulation_issue: str | None = None
    proposed_change: str | None = None
    expected_effect: str | None = None
    risk_of_change: str | None = None
    failure_class: str = "UNKNOWN"


@dataclass
class LearningPatch(EvidenceEnvelope):
    patch_id: str = field(default_factory=lambda: new_id("patch"))
    source_reflection_ids: list[str] = field(default_factory=list)
    change_scope: str = ""
    affected_strategy: str = ""
    affected_regime: str = ""
    before_behavior: str = ""
    after_behavior: str = ""
    replay_result: str | None = None
    walk_forward_result: str | None = None
    oos_result: str | None = None
    sample_sufficiency: str = "UNKNOWN"
    risk_review: str | None = None
    status: str = "PROPOSED"
    applied_at: int | None = None


@dataclass
class WorkerHealth(EvidenceEnvelope):
    worker_id: str = ""
    worker_type: str = ""
    owner_id: str = ""
    health: str = "DISABLED"
    current_stage: str = ""
    last_started_at: int | None = None
    last_progress_at: int | None = None
    last_completed_at: int | None = None
    queue_depth: int = 0
    last_error: str | None = None
    consecutive_failures: int = 0
    stalled: bool = False
    stall_reason: str | None = None


def assert_transition(cur: str, nxt: str) -> None:
    c = LifecycleState(cur)
    n = LifecycleState(nxt)
    if n not in LEGAL_TRANSITIONS.get(c, set()):
        raise ValueError(f"illegal_transition:{cur}->{nxt}")


def strip_fleet_id(payload: dict[str, Any]) -> dict[str, Any]:
    """Backward-compat adapter: read fleet_id then drop it from formal schema."""
    out = dict(payload)
    if "fleet_id" in out:
        out.pop("fleet_id", None)
        out["deprecated_fleet_id_ignored"] = True
    return out
