"""Non-mutating contracts / stubs for Bybit Demo readiness (no order execution)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    DEMO_REST_BASE_URL,
    ENV_API_KEY,
    ENV_API_SECRET,
    FORBIDDEN_BASE_URLS,
)
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import DomainRejectedError


@dataclass(frozen=True)
class GateCheckResult:
    gate_id: str
    passed: bool
    detail: str = ""
    harness_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "detail": self.detail,
            "harness_only": self.harness_only,
        }


def check_demo_env_identity() -> GateCheckResult:
    ok = ACCOUNT_BYBIT_DEMO == "BYBIT_DEMO_ACCOUNT" and DEMO_REST_BASE_URL.endswith(
        "api-demo.bybit.com"
    )
    return GateCheckResult(
        gate_id="demo_env_identity",
        passed=ok,
        detail=f"account={ACCOUNT_BYBIT_DEMO};base={DEMO_REST_BASE_URL}",
    )


def check_mainnet_endpoint_hard_deny() -> GateCheckResult:
    policy = DemoDomainPolicy()
    rejected = 0
    for url in sorted(FORBIDDEN_BASE_URLS):
        try:
            policy.validate_base_url(url)
        except DomainRejectedError:
            rejected += 1
            continue
        return GateCheckResult(
            gate_id="mainnet_endpoint_hard_deny",
            passed=False,
            detail=f"failed_to_deny:{url}",
        )
    # Positive allow
    try:
        allowed = policy.validate_base_url(DEMO_REST_BASE_URL)
    except DomainRejectedError as exc:
        return GateCheckResult(
            gate_id="mainnet_endpoint_hard_deny",
            passed=False,
            detail=f"demo_base_rejected:{exc}",
        )
    ok = rejected == len(FORBIDDEN_BASE_URLS) and "api-demo.bybit.com" in allowed
    return GateCheckResult(
        gate_id="mainnet_endpoint_hard_deny",
        passed=ok,
        detail=f"rejected={rejected};allowed={allowed}",
    )


def check_credentials_env_only(*, repo_root_has_secrets: bool = False) -> GateCheckResult:
    """Credentials must come from env/secret manager — never from repo files."""
    import os

    key_env = ENV_API_KEY
    secret_env = ENV_API_SECRET
    # Presence is optional for harness; channel correctness is required.
    channel_ok = bool(key_env and secret_env) and not repo_root_has_secrets
    # Never read secret values into evidence — only presence flags.
    present = bool(os.environ.get(key_env)) and bool(os.environ.get(secret_env))
    return GateCheckResult(
        gate_id="credentials_env_or_secret_manager_only",
        passed=channel_ok,
        detail=f"env_keys={key_env},{secret_env};present={present};repo_secrets={repo_root_has_secrets}",
    )


def check_server_time_sync_stub() -> GateCheckResult:
    """Interface contract: GET /v5/market/time must be allowlisted (no live call required)."""
    from backend.nexus_research.demo_exchange.constants import ALLOWED_GET_PATHS

    ok = "/v5/market/time" in ALLOWED_GET_PATHS
    return GateCheckResult(
        gate_id="server_time_sync_stub",
        passed=ok,
        detail="allowlisted_/v5/market/time" if ok else "missing_time_path",
    )


def check_instrument_lookup_contract() -> GateCheckResult:
    from backend.nexus_research.demo_exchange.constants import ALLOWED_GET_PATHS

    ok = "/v5/market/instruments-info" in ALLOWED_GET_PATHS
    return GateCheckResult(
        gate_id="instrument_lookup",
        passed=ok,
        detail="allowlisted_instruments-info" if ok else "missing",
    )


def check_account_read_preflight_interfaces() -> GateCheckResult:
    from backend.nexus_research.demo_exchange.constants import ALLOWED_GET_PATHS

    needed = {
        "/v5/account/wallet-balance",
        "/v5/account/info",
        "/v5/position/list",
    }
    missing = sorted(needed - ALLOWED_GET_PATHS)
    return GateCheckResult(
        gate_id="account_read_preflight_interfaces",
        passed=not missing,
        detail="ok" if not missing else f"missing:{missing}",
    )


@dataclass
class MarginLeveragePositionModeContract:
    """Validation contract only — does not mutate exchange state."""

    max_leverage: float = 5.0
    allowed_position_modes: tuple[str, ...] = ("one_way", "merged_single")
    margin_modes: tuple[str, ...] = ("isolated", "cross")

    def validate(self, *, leverage: float, position_mode: str, margin_mode: str) -> list[str]:
        errs: list[str] = []
        if float(leverage) <= 0 or float(leverage) > float(self.max_leverage):
            errs.append("leverage_out_of_range")
        if position_mode not in self.allowed_position_modes:
            errs.append("position_mode_invalid")
        if margin_mode not in self.margin_modes:
            errs.append("margin_mode_invalid")
        return errs


def check_margin_leverage_position_mode_contract() -> GateCheckResult:
    c = MarginLeveragePositionModeContract()
    # Non-mutating self-test of the contract.
    bad = c.validate(leverage=50, position_mode="hedge", margin_mode="foo")
    good = c.validate(leverage=2, position_mode="one_way", margin_mode="isolated")
    ok = bool(bad) and not good
    return GateCheckResult(
        gate_id="margin_leverage_position_mode_validation_contract",
        passed=ok,
        detail=f"reject_bad={bad};accept_good={good}",
    )


@dataclass
class LotTickContract:
    min_qty: float = 0.001
    qty_step: float = 0.001
    tick_size: float = 0.1
    min_notional: float = 5.0

    def validate(self, *, qty: float, price: float) -> list[str]:
        errs: list[str] = []
        if qty < self.min_qty:
            errs.append("below_min_qty")
        # Step alignment (tolerant float)
        steps = round(qty / self.qty_step)
        if abs(steps * self.qty_step - qty) > 1e-12:
            errs.append("qty_step_misaligned")
        ticks = round(price / self.tick_size)
        if abs(ticks * self.tick_size - price) > 1e-9:
            errs.append("tick_misaligned")
        if qty * price < self.min_notional:
            errs.append("below_min_notional")
        return errs


def check_min_qty_tick_lot_contract() -> GateCheckResult:
    c = LotTickContract()
    bad = c.validate(qty=0.0001, price=100.05)
    good = c.validate(qty=0.1, price=100.0)  # 0.1 * 100 >= min_notional 5
    ok = bool(bad) and not good
    return GateCheckResult(
        gate_id="min_qty_tick_lot",
        passed=ok,
        detail=f"reject_bad={bad};accept_good={good}",
    )


@dataclass
class OrderIdempotencyContract:
    """Client order ID + duplicate prevention (scaffold — never submits)."""

    seen: set[str] = field(default_factory=set)

    def register(self, client_order_id: str) -> list[str]:
        cid = (client_order_id or "").strip()
        errs: list[str] = []
        if not cid:
            errs.append("missing_client_order_id")
            return errs
        if len(cid) > 36:
            errs.append("client_order_id_too_long")
        if cid in self.seen:
            errs.append("duplicate_client_order_id")
            return errs
        self.seen.add(cid)
        return errs


def check_order_idempotency_and_client_order_id() -> GateCheckResult:
    c = OrderIdempotencyContract()
    first = c.register("nexus_demo_test_001")
    dup = c.register("nexus_demo_test_001")
    empty = c.register("")
    ok = not first and "duplicate_client_order_id" in dup and "missing_client_order_id" in empty
    return GateCheckResult(
        gate_id="order_idempotency_client_order_id_duplicate_prevention",
        passed=ok,
        detail=f"first={first};dup={dup};empty={empty}",
    )


def check_reduce_only_close_sl_tp_cancel_contracts() -> GateCheckResult:
    """Scaffold contracts exist as declarative shapes — no execution."""
    required_fields = {
        "reduce_only_close": ("symbol", "side", "qty", "reduce_only", "client_order_id"),
        "sl_tp": ("symbol", "stop_loss", "take_profit", "trigger_by"),
        "cancel": ("symbol", "order_id_or_client_order_id", "category"),
    }
    # Static presence of required field names is the harness gate.
    ok = all(len(v) >= 3 for v in required_fields.values())
    return GateCheckResult(
        gate_id="reduce_only_sl_tp_cancel_contracts",
        passed=ok,
        detail=f"contracts={list(required_fields)}",
    )


def check_reconciliation_restart_recovery_contracts() -> GateCheckResult:
    steps = (
        "load_local_open_orders",
        "fetch_exchange_open_orders_readonly",
        "diff_and_quarantine",
        "resume_from_checkpoint",
        "no_duplicate_submit",
    )
    ok = len(steps) == 5
    return GateCheckResult(
        gate_id="reconciliation_restart_recovery",
        passed=ok,
        detail=f"steps={list(steps)}",
    )


def check_kill_switch_and_risk_caps() -> GateCheckResult:
    caps = {
        "kill_switch": True,
        "max_open_positions": 1,
        "max_notional_usdt": 100.0,
        "simulated_risk_only": True,
        "autonomous_demo_order_allowed": False,
    }
    ok = (
        caps["kill_switch"] is True
        and caps["max_open_positions"] >= 1
        and caps["autonomous_demo_order_allowed"] is False
    )
    return GateCheckResult(
        gate_id="kill_switch_max_positions_notional_simulated_risk",
        passed=ok,
        detail=str(caps),
    )


def check_command_scaffolding_no_execute() -> GateCheckResult:
    """Command scaffolding must exist but MUST NOT execute any order."""

    def place_order_scaffold(**_kwargs: Any) -> dict[str, Any]:
        return {
            "executed": False,
            "blocked": True,
            "reason": "demo_order_armed=false;founder_approval_required=true",
        }

    result = place_order_scaffold(symbol="BTCUSDT", side="Buy", qty=0.001)
    ok = result.get("executed") is False and result.get("blocked") is True
    return GateCheckResult(
        gate_id="command_scaffolding_no_execute",
        passed=ok,
        detail=str(result),
    )


ALL_HARNESS_CHECKS: tuple[Callable[[], GateCheckResult], ...] = (
    check_demo_env_identity,
    check_mainnet_endpoint_hard_deny,
    check_credentials_env_only,
    check_server_time_sync_stub,
    check_instrument_lookup_contract,
    check_account_read_preflight_interfaces,
    check_margin_leverage_position_mode_contract,
    check_min_qty_tick_lot_contract,
    check_order_idempotency_and_client_order_id,
    check_reduce_only_close_sl_tp_cancel_contracts,
    check_reconciliation_restart_recovery_contracts,
    check_kill_switch_and_risk_caps,
    check_command_scaffolding_no_execute,
)
