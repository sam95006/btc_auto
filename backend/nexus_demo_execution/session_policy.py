"""Shared policy objects for 6H V2 and 12H V3 bounded autonomous sessions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.nexus_demo_execution import session_limits as v2
from backend.nexus_demo_execution import v3_policy as v3


@dataclass(frozen=True)
class BoundedSessionPolicy:
    label: str
    session_gate_name: str
    allowed_gates: frozenset[str]
    policy_version: str
    schema_version: str
    session_duration_sec: int
    max_total_entry_orders: int
    max_completed_trades: int
    margin_per_trade: float
    leverage: int
    margin_mode: str
    max_session_net_loss: float
    max_single_trade_net_loss: float
    max_consecutive_losses: int
    max_bad_process_outcomes: int
    max_hold_sec: int
    protection_verify_deadline_sec: int
    cycle_interval_sec: int
    supervisor_poll_sec: int
    checkpoint_offsets_sec: tuple[int, ...]
    session_id_prefix: str
    thread_name: str
    export_subdir: str
    recommendations: tuple[str, ...]
    founder_approval_env: str
    founder_gate_env_required: bool = True
    controller_type: str = "FULL_AUTONOMOUS_ENGINE"


def policy_6h_v2() -> BoundedSessionPolicy:
    return BoundedSessionPolicy(
        label="6H_V2",
        session_gate_name=v2.SESSION_GATE_NAME,
        allowed_gates=frozenset({v2.SESSION_GATE_NAME, v2.SESSION_GATE_NAME_LEGACY}),
        policy_version=v2.POLICY_VERSION,
        schema_version=v2.SCHEMA_VERSION,
        session_duration_sec=v2.SESSION_DURATION_SEC,
        max_total_entry_orders=v2.MAX_TOTAL_ENTRY_ORDERS,
        max_completed_trades=v2.MAX_COMPLETED_TRADE_CASES,
        margin_per_trade=v2.MARGIN_PER_TRADE_CAP,
        leverage=v2.FIXED_LEVERAGE,
        margin_mode=v2.MARGIN_MODE,
        max_session_net_loss=v2.MAX_SESSION_NET_LOSS,
        max_single_trade_net_loss=v2.MAX_SINGLE_TRADE_NET_LOSS,
        max_consecutive_losses=v2.MAX_CONSECUTIVE_LOSSES,
        max_bad_process_outcomes=v2.MAX_BAD_PROCESS_OUTCOMES,
        max_hold_sec=v2.MAX_HOLD_SEC,
        protection_verify_deadline_sec=v2.PROTECTION_VERIFY_DEADLINE_SEC,
        cycle_interval_sec=v2.CYCLE_INTERVAL_SEC,
        supervisor_poll_sec=v2.SUPERVISOR_POLL_SEC,
        checkpoint_offsets_sec=tuple(v2.CHECKPOINT_OFFSETS_SEC),
        session_id_prefix="NEXUS-DEMO-6H-V2",
        thread_name="bounded-autonomous-6h-v2",
        export_subdir="demo_validation_6h_v2",
        recommendations=(
            "DEMO_AUTONOMOUS_6H_V2_PASS",
            "DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS",
            "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION",
            "DEMO_AUTONOMOUS_6H_V2_FAILED",
        ),
        founder_approval_env="FOUNDER_6H_APPROVED",
        controller_type="FULL_AUTONOMOUS_ENGINE",
    )


def policy_12h_v3() -> BoundedSessionPolicy:
    return BoundedSessionPolicy(
        label="12H_V3",
        session_gate_name=v3.SESSION_GATE_NAME,
        allowed_gates=frozenset({v3.SESSION_GATE_NAME}),
        policy_version=v3.POLICY_VERSION,
        schema_version=v3.SCHEMA_VERSION,
        session_duration_sec=v3.SESSION_DURATION_SEC,
        max_total_entry_orders=v3.MAX_TOTAL_ENTRY_ORDERS,
        max_completed_trades=v3.MAX_COMPLETED_TRADE_CASES,
        margin_per_trade=v3.MARGIN_PER_TRADE_CAP,
        leverage=v3.FIXED_LEVERAGE,
        margin_mode=v3.MARGIN_MODE,
        max_session_net_loss=v3.MAX_SESSION_NET_LOSS,
        max_single_trade_net_loss=v3.MAX_SINGLE_TRADE_NET_LOSS,
        max_consecutive_losses=v3.MAX_CONSECUTIVE_LOSSES,
        max_bad_process_outcomes=v3.MAX_BAD_PROCESS_OUTCOMES,
        max_hold_sec=v3.MAX_HOLD_SEC,
        protection_verify_deadline_sec=v3.PROTECTION_VERIFY_DEADLINE_SEC,
        cycle_interval_sec=v3.CYCLE_INTERVAL_SEC,
        supervisor_poll_sec=v3.SUPERVISOR_POLL_SEC,
        checkpoint_offsets_sec=tuple(v3.CHECKPOINT_OFFSETS_SEC),
        session_id_prefix="NEXUS-DEMO-12H-V3",
        thread_name="bounded-autonomous-12h-v3",
        export_subdir="demo_validation_12h_v3",
        recommendations=(
            "DEMO_AUTONOMOUS_12H_V3_PASS",
            "DEMO_AUTONOMOUS_12H_V3_PASS_WITH_FINDINGS",
            "DEMO_AUTONOMOUS_12H_V3_INCONCLUSIVE_NO_EXECUTION",
            "DEMO_AUTONOMOUS_12H_V3_FAILED",
            "DEMO_AUTONOMOUS_12H_V3_EXTENDED_OBSERVATION_COMPLETED",
        ),
        founder_approval_env="FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3",
        controller_type="FULL_AUTONOMOUS_ENGINE",
    )


def policy_short_v1() -> BoundedSessionPolicy:
    return BoundedSessionPolicy(
        label="SHORT_V1",
        session_gate_name="DEMO_CERTIFIED_SHORT_BOUNDED_V1",
        allowed_gates=frozenset({"DEMO_CERTIFIED_SHORT_BOUNDED_V1"}),
        policy_version="demo-certified-short-bounded-v1",
        schema_version="demo_validation_short_v1",
        session_duration_sec=60 * 60,
        max_total_entry_orders=1,
        max_completed_trades=1,
        margin_per_trade=v2.MARGIN_PER_TRADE_CAP,
        leverage=v2.FIXED_LEVERAGE,
        margin_mode=v2.MARGIN_MODE,
        max_session_net_loss=v2.MAX_SESSION_NET_LOSS,
        max_single_trade_net_loss=v2.MAX_SINGLE_TRADE_NET_LOSS,
        max_consecutive_losses=v2.MAX_CONSECUTIVE_LOSSES,
        max_bad_process_outcomes=v2.MAX_BAD_PROCESS_OUTCOMES,
        max_hold_sec=v2.MAX_HOLD_SEC,
        protection_verify_deadline_sec=v2.PROTECTION_VERIFY_DEADLINE_SEC,
        cycle_interval_sec=v2.CYCLE_INTERVAL_SEC,
        supervisor_poll_sec=v2.SUPERVISOR_POLL_SEC,
        checkpoint_offsets_sec=(0, 15 * 60, 30 * 60, 45 * 60, 60 * 60),
        session_id_prefix="NEXUS-DEMO-SHORT-V1",
        thread_name="bounded-certified-short-v1",
        export_subdir="demo_validation_short_v1",
        recommendations=(
            "DEMO_CERTIFIED_SHORT_V1_PASS",
            "DEMO_CERTIFIED_SHORT_V1_PASS_WITH_FINDINGS",
            "DEMO_CERTIFIED_SHORT_V1_INCONCLUSIVE_NO_EXECUTION",
            "DEMO_CERTIFIED_SHORT_V1_FAILED",
            "DEMO_CERTIFIED_SHORT_V1_FAILED_LEARNING_CLOSURE",
        ),
        founder_approval_env="FOUNDER_SHORT_BOUNDED_APPROVED",
        controller_type="FULL_AUTONOMOUS_ENGINE",
    )


SessionIdFactory = Callable[[str], str]
