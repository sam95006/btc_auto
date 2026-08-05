"""Canonical authority registry for Private Core domains.

Lane H owns this registry. Competing implementations discovered during audit are
recorded as non-canonical competitors with removal recommendations — they are
NOT deleted in this phase (hard ban: no mass-delete of compatibility modules).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

REGISTRY_SCHEMA = "nexus_canonical_authority_registry_v1"
REGISTRY_VERSION = "v11.1.checkpoint_authority"

AUTHORITY_DOMAINS: tuple[str, ...] = (
    "execution",
    "fill",
    "cost",
    "risk",
    "lifecycle",
    "checkpoint",
    "provider_retry",
)


@dataclass(frozen=True)
class CompetitorRecord:
    """A non-canonical module that still claims or implements authority semantics."""

    module: str
    symbol: str | None
    role: str  # compatibility_shim | parallel_lane | legacy_product | fixture_tool | obsolete_entry
    severity: str  # critical | high | medium | low | informational
    notes: str
    recommended_action: str  # retain_compat | migrate_callers | quarantine | future_remove
    delete_now: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuthorityRecord:
    """One canonical authority for a domain (exactly one per scope)."""

    domain: str
    authority_id: str
    canonical_module: str
    canonical_symbol: str
    contract_module: str | None
    scope: str
    status: str  # active | active_compat_present | contested
    invariants: tuple[str, ...] = ()
    competitors: tuple[CompetitorRecord, ...] = ()
    contract_keys: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["invariants"] = list(self.invariants)
        d["contract_keys"] = list(self.contract_keys)
        d["competitors"] = [c.to_dict() for c in self.competitors]
        return d


def _records() -> tuple[AuthorityRecord, ...]:
    return (
        AuthorityRecord(
            domain="execution",
            authority_id="private_core.execution.simulator_v1_1",
            canonical_module="backend.nexus_execution.execution_simulator_v1_1",
            canonical_symbol="AutonomousExecutionSimulatorV11",
            contract_module="backend.nexus_execution.contracts",
            scope="private_core_simulated_session",
            status="active_compat_present",
            invariants=(
                "SIMULATED_NO_EXCHANGE_WRITE",
                "CANONICAL_EXECUTION_ENGINE_COUNT==1",
                "session_traffic_via_orchestrator_adapter_v1_only",
            ),
            contract_keys=("OrderIntent", "OrderRecord", "PositionRecord", "CompletedTrade"),
            competitors=(
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_simulator_v1_1",
                    symbol="AutonomousExecutionSimulatorV1_1",
                    role="compatibility_shim",
                    severity="high",
                    notes=(
                        "Documented COMPATIBILITY ADAPTER ONLY; still contains full fill/cost/risk "
                        "logic and can be mistaken for a second authority."
                    ),
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_simulator_v1",
                    symbol="AutonomousExecutionSimulatorV1",
                    role="compatibility_shim",
                    severity="high",
                    notes="Older V1 simulator; parallel fee/fill/risk constants vs canonical engine.",
                    recommended_action="future_remove",
                ),
                CompetitorRecord(
                    module="backend.nexus_real_shadow.real_price_shadow",
                    symbol="simulate_fill",
                    role="parallel_lane",
                    severity="medium",
                    notes="Shadow-lane fill simulation; must not feed Session orchestrator authority.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.trading.paper_order_execution_engine",
                    symbol=None,
                    role="legacy_product",
                    severity="medium",
                    notes="Product paper execution path outside Private Core simulated contract.",
                    recommended_action="quarantine",
                ),
                CompetitorRecord(
                    module="backend.autonomy.pure_ai_execution",
                    symbol=None,
                    role="legacy_product",
                    severity="medium",
                    notes="Legacy autonomy execution bridge; not Session→Execution adapter.",
                    recommended_action="quarantine",
                ),
                CompetitorRecord(
                    module="backend.trading.binance_testnet_execution_engine",
                    symbol=None,
                    role="legacy_product",
                    severity="medium",
                    notes="Binance testnet execution engine; product lane, not Private Core Session authority.",
                    recommended_action="quarantine",
                ),
                CompetitorRecord(
                    module="backend.trading.binance_spot_testnet_execution_engine",
                    symbol=None,
                    role="legacy_product",
                    severity="medium",
                    notes="Binance spot testnet execution engine; product lane.",
                    recommended_action="quarantine",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.security_mutation_v11.constants",
                    symbol=None,
                    role="fixture_tool",
                    severity="low",
                    notes=(
                        "V11 security mutation red-team fixture constants only; "
                        "must never become Session→Execution authority."
                    ),
                    recommended_action="retain_compat",
                ),
            ),
            notes=(
                "Cross-lane Session→Execution bridge is "
                "backend.nexus_execution.orchestrator_adapter_v1."
            ),
        ),
        AuthorityRecord(
            domain="fill",
            authority_id="private_core.fill.engine_v1_1",
            canonical_module="backend.nexus_execution.fill_engine",
            canonical_symbol="try_fill",
            contract_module="backend.nexus_execution.contracts",
            scope="private_core_simulated_session",
            status="active_compat_present",
            invariants=(
                "candle_touch_alone_never_fills",
                "queue_aware_conservative_partials",
                "same_bar_stop_and_target_BLOCKED_AMBIGUOUS",
            ),
            contract_keys=("FillEvent",),
            competitors=(
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_simulator_v1_1",
                    symbol="AutonomousExecutionSimulatorV1_1",
                    role="compatibility_shim",
                    severity="critical",
                    notes="Embedded fill policy duplicates fill_engine semantics.",
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_real_shadow.real_price_shadow",
                    symbol="simulate_fill",
                    role="parallel_lane",
                    severity="medium",
                    notes="Independent shadow fill path.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_models_v1_1",
                    symbol="FILL_POLICY_DOC",
                    role="compatibility_shim",
                    severity="medium",
                    notes="Shared V1.1 fill policy docs/models for compat simulator.",
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_simulator_v1",
                    symbol=None,
                    role="compatibility_shim",
                    severity="high",
                    notes="V1 simulator embeds fill logic; supersede via orchestrator adapter.",
                    recommended_action="future_remove",
                ),
            ),
            notes="Fill authority is subordinate to canonical execution simulator.",
        ),
        AuthorityRecord(
            domain="cost",
            authority_id="private_core.cost.model_v1_1",
            canonical_module="backend.nexus_execution.cost_model",
            canonical_symbol="COST_MODEL_VERSION",
            contract_module="backend.nexus_execution.contracts",
            scope="private_core_simulated_session",
            status="contested",
            invariants=(
                "exact_decimal_cost_bridge",
                "gross_minus_components_equals_net",
            ),
            contract_keys=("CostBridge", "COST_MODEL_VERSION"),
            competitors=(
                CompetitorRecord(
                    module="backend.nexus_strategy_engine.cost_semantics",
                    symbol="COST_MODEL_VERSION",
                    role="parallel_lane",
                    severity="critical",
                    notes=(
                        "Divergent COST_MODEL_VERSION string "
                        "(NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1 vs founder-conservative-v1-1-*). "
                        "Contract drift risk for strategy↔execution evidence."
                    ),
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_demo_execution.trade_geometry",
                    symbol="estimate_costs",
                    role="parallel_lane",
                    severity="high",
                    notes="Demo geometry cost estimator; separate fee constants.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_demo_execution.fee_rate",
                    symbol=None,
                    role="parallel_lane",
                    severity="medium",
                    notes="Demo fee-rate helpers; must not override simulated cost bridge.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_simulator_v1_1",
                    symbol="TAKER_FEE",
                    role="compatibility_shim",
                    severity="high",
                    notes="Hard-coded TAKER_FEE/MAKER_FEE float path vs Decimal cost_model.",
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_edge_discovery.taxonomy_audit",
                    symbol="COST_MODEL_VERSION",
                    role="fixture_tool",
                    severity="low",
                    notes="Taxonomy audit references a cost model version for evidence labeling only.",
                    recommended_action="retain_compat",
                ),
            ),
            notes="Canonical version string: founder-conservative-v1-1-2026-08-05",
        ),
        AuthorityRecord(
            domain="risk",
            authority_id="private_core.risk.gates_v1_1",
            canonical_module="backend.nexus_execution.risk_gates",
            canonical_symbol="RiskLimits",
            contract_module="backend.nexus_execution.risk_gates",
            scope="private_core_simulated_session",
            status="active_compat_present",
            invariants=(
                "max_leverage_ceiling_50",
                "ISOLATED_only",
                "FORBIDDEN_ACTIONS_immutable",
            ),
            contract_keys=("RiskLimits", "FORBIDDEN_ACTIONS", "MAX_LEVERAGE_CEILING"),
            competitors=(
                CompetitorRecord(
                    module="backend.risk.risk_control_engine",
                    symbol=None,
                    role="legacy_product",
                    severity="medium",
                    notes="Product risk engine; out of Session simulated gate scope.",
                    recommended_action="quarantine",
                ),
                CompetitorRecord(
                    module="backend.nexus_research.risk_engine",
                    symbol=None,
                    role="parallel_lane",
                    severity="medium",
                    notes="Research risk engine; must not override execution risk_gates.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_demo_execution.risk_sizing",
                    symbol=None,
                    role="parallel_lane",
                    severity="medium",
                    notes="Demo sizing helpers.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_simulator_v1_1",
                    symbol="FORBIDDEN_ACTIONS",
                    role="compatibility_shim",
                    severity="high",
                    notes="Duplicated forbidden-action set inside compat simulator.",
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.execution_simulator_v1",
                    symbol="FORBIDDEN_ACTIONS",
                    role="compatibility_shim",
                    severity="high",
                    notes="V1 simulator duplicates forbidden-action risk constants.",
                    recommended_action="future_remove",
                ),
                CompetitorRecord(
                    module="backend.nexus_research.demo_exchange.identity",
                    symbol=None,
                    role="parallel_lane",
                    severity="low",
                    notes="Demo identity helpers may reference risk/margin fields; not Session risk_gates.",
                    recommended_action="retain_compat",
                ),
            ),
            notes="Product/demo risk modules remain lane-local; Session uses risk_gates only.",
        ),
        AuthorityRecord(
            domain="lifecycle",
            authority_id="private_core.lifecycle.session_sm_v1_1",
            canonical_module="backend.nexus_autonomy.session_state_machine",
            canonical_symbol="CANONICAL_STATES",
            contract_module="backend.nexus_autonomy.session_state_machine",
            scope="private_core_session_orchestration",
            status="contested",
            invariants=(
                "fail_closed_invalid_transition",
                "terminal_COMPLETED_BLOCKED_FAILED_SAFE",
            ),
            contract_keys=("CANONICAL_STATES", "TERMINAL_STATES", "VALID_TRANSITIONS"),
            competitors=(
                CompetitorRecord(
                    module="backend.nexus_private_control.state_machine",
                    symbol="CANONICAL_STATES",
                    role="parallel_lane",
                    severity="critical",
                    notes=(
                        "Founder control-plane lifecycle uses a different state vocabulary "
                        "(IDLE/STARTING/.../KILLED) vs Session SM. Dual lifecycle authorities."
                    ),
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_research.demo_execution.state_machine",
                    symbol="DemoOrderStateMachine",
                    role="parallel_lane",
                    severity="medium",
                    notes="Demo order lifecycle (17 states); lane-local.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_research.demo_autonomous.position_lifecycle",
                    symbol="DemoPositionLifecycleController",
                    role="parallel_lane",
                    severity="medium",
                    notes="Demo position lifecycle; not Session orchestrator authority.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_research.demo_exchange.state_machine",
                    symbol="DemoStateMachine",
                    role="parallel_lane",
                    severity="low",
                    notes="Demo exchange account state machine.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.qualification_promotion_sm",
                    symbol=None,
                    role="parallel_lane",
                    severity="medium",
                    notes="Qualification promotion state machine; separate from Session lifecycle.",
                    recommended_action="retain_compat",
                ),
            ),
            notes=(
                "Two legitimate Private Core lifecycles exist (Session vs Control Plane). "
                "They must remain scoped; do not merge silently."
            ),
        ),
        AuthorityRecord(
            domain="checkpoint",
            authority_id="private_core.checkpoint.envelope_v1",
            canonical_module="backend.nexus_checkpoint.store",
            canonical_symbol="CanonicalCheckpointStore",
            contract_module="backend.nexus_checkpoint.envelope",
            scope="private_core_canonical_envelope",
            status="active_compat_present",
            invariants=(
                "ambiguous_state_routes_to_BLOCKED_AMBIGUOUS",
                "no_silent_resume",
                "atomic_temp_fsync_rename",
                "checksum_verify_on_read_write",
                "lkg_pointer_required_for_restore",
                "no_destructive_live_v23_migration",
                "CANONICAL_CHECKPOINT_ENVELOPE_COUNT==1",
            ),
            contract_keys=(
                "build_envelope",
                "validate_envelope",
                "detect_corruption",
                "CanonicalCheckpointStore",
                "REQUIRED_ENVELOPE_FIELDS",
            ),
            competitors=(
                CompetitorRecord(
                    module="backend.nexus_recovery.crash_recovery",
                    symbol="recover_from_checkpoint",
                    role="parallel_lane",
                    severity="medium",
                    notes=(
                        "Session crash recovery consumes durability LKG; must restore via "
                        "envelope/LKG contracts — does not own envelope schema."
                    ),
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_private_control.checkpoint",
                    symbol="CheckpointStore",
                    role="parallel_lane",
                    severity="medium",
                    notes=(
                        "Control-plane payload owner; wrap via "
                        "adapters.wrap_control_plane_payload before cross-domain resume."
                    ),
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_reflection.checkpoint",
                    symbol="checkpoint_path",
                    role="parallel_lane",
                    severity="medium",
                    notes=(
                        "Blind Reflection V2.3 payload schema v4 owner; wrap via "
                        "adapters.wrap_reflection_payload (dry-run before live migrate)."
                    ),
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_decision.checkpoint",
                    symbol="DecisionCheckpointStore",
                    role="parallel_lane",
                    severity="medium",
                    notes="Decision lifecycle payload owner; wrap via adapters.wrap_decision_payload.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_edge_discovery.quota_aware_v23",
                    symbol="checkpoint_path",
                    role="compatibility_shim",
                    severity="low",
                    notes="Edge-discovery checkpoint helpers; overlaps reflection payload path.",
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_reflection.v23_resume_v10",
                    symbol="checkpoint_dest",
                    role="parallel_lane",
                    severity="low",
                    notes="V10 resume destination helper; payload-scoped.",
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="backend.nexus_autonomy.session_orchestrator_v1",
                    symbol="checkpoint",
                    role="obsolete_entry",
                    severity="low",
                    notes="V1 orchestrator checkpoint method; prefer envelope store + V1.1 recovery.",
                    recommended_action="future_remove",
                ),
            ),
            notes=(
                "V11.1 C4: one canonical envelope (nexus_checkpoint_envelope_v1). "
                "Subsystems retain payload schema ownership; cross-domain resume requires "
                "explicit adapters. Live V2.3 migration is dry-run only."
            ),
        ),
        AuthorityRecord(
            domain="provider_retry",
            authority_id="private_core.provider.retry_policy_v1",
            canonical_module="backend.nexus_provider.retry_policy",
            canonical_symbol="parse_retry_after",
            contract_module="backend.nexus_provider",
            scope="private_core_provider_transport",
            status="active",
            invariants=(
                "retry_after_http_date_or_seconds",
                "bounded_jittered_exponential_backoff",
                "429_never_ai_quality_failure",
                "single_retry_algorithm_authority",
            ),
            contract_keys=(
                "parse_retry_after",
                "parse_rate_limit_reset",
                "parse_quota_reset_at",
                "backoff_with_jitter",
                "exponential_backoff_with_jitter",
                "compute_resume_wait_s",
                "next_resume_iso",
                "ProviderCircuitBreaker",
                "TokenBucket",
                "classify_transport_status",
            ),
            competitors=(
                CompetitorRecord(
                    module="backend.nexus_edge_discovery.provider_transport_v23",
                    symbol="CircuitBreaker",
                    role="adapter_lane",
                    severity="low",
                    notes=(
                        "V2.3 transport facade: re-exports / wraps canonical "
                        "backend.nexus_provider.retry_policy + ProviderCircuitBreaker."
                    ),
                    recommended_action="retain_compat",
                ),
                CompetitorRecord(
                    module="tools.research.stage4_provider_chain",
                    symbol="Stage4ProviderCircuitBreaker",
                    role="fixture_tool",
                    severity="high",
                    notes="Stage4 research circuit breaker; parallel to ProviderCircuitBreaker.",
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.nexus_real_shadow.http_client",
                    symbol="CircuitBreakerState",
                    role="parallel_lane",
                    severity="medium",
                    notes="Shadow HTTP client embeds independent retry/backoff/circuit.",
                    recommended_action="migrate_callers",
                ),
                CompetitorRecord(
                    module="backend.trading.binance_rate_limit_guard",
                    symbol=None,
                    role="legacy_product",
                    severity="low",
                    notes="Exchange-specific rate-limit guard outside provider package.",
                    recommended_action="quarantine",
                ),
                CompetitorRecord(
                    module="backend.nexus_research.runtime_supervisor",
                    symbol=None,
                    role="parallel_lane",
                    severity="low",
                    notes="Job registry retry/backoff; not LLM provider transport.",
                    recommended_action="retain_compat",
                ),
            ),
            notes=(
                "Canonical provider retry lives in backend.nexus_provider.retry_policy; "
                "lanes must import it. Provider-specific VALUES may differ; algorithm must not."
            ),
        ),
    )


_REGISTRY: dict[str, AuthorityRecord] | None = None


def list_authorities() -> tuple[AuthorityRecord, ...]:
    return _records()


def get_authority(domain: str) -> AuthorityRecord:
    for rec in _records():
        if rec.domain == domain:
            return rec
    raise KeyError(f"unknown authority domain: {domain}")


def build_canonical_registry() -> dict[str, Any]:
    global _REGISTRY
    records = list_authorities()
    by_domain = {r.domain: r.to_dict() for r in records}
    contested = [r.domain for r in records if r.status == "contested"]
    critical = []
    for r in records:
        for c in r.competitors:
            if c.severity == "critical":
                critical.append(
                    {
                        "domain": r.domain,
                        "module": c.module,
                        "symbol": c.symbol,
                        "notes": c.notes,
                        "recommended_action": c.recommended_action,
                    }
                )
    payload = {
        "schema": REGISTRY_SCHEMA,
        "registry_version": REGISTRY_VERSION,
        "lane": "V11_H_AUTHORITY_CONSOLIDATION",
        "domains": list(AUTHORITY_DOMAINS),
        "authorities": [r.to_dict() for r in records],
        "by_domain": by_domain,
        "summary": {
            "domain_count": len(records),
            "contested_domains": contested,
            "critical_competitor_count": len(critical),
            "critical_competitors": critical,
            "deletion_policy": "recommend_only_no_mass_delete",
        },
    }
    _REGISTRY = {r.domain: r for r in records}
    return payload


def iter_baseline_claimants() -> Iterable[dict[str, str]]:
    """Flatten canonical + competitor modules for CI baseline comparison."""
    for rec in list_authorities():
        yield {
            "domain": rec.domain,
            "module": rec.canonical_module,
            "role": "canonical",
            "authority_id": rec.authority_id,
        }
        for c in rec.competitors:
            yield {
                "domain": rec.domain,
                "module": c.module,
                "role": c.role,
                "authority_id": rec.authority_id,
            }
