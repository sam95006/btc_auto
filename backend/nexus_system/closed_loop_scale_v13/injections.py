"""Fault / injection catalog for V13-G closed-loop scale."""
from __future__ import annotations

# Founder-required coverage classes for V13-G.
SCALE_FAULT_CLASSES: tuple[str, ...] = (
    "multi_symbol",
    "multi_regime",
    "provider_outage",
    "partial_fills",
    "cancel_replace",
    "clock_rollback",
    "disk_pressure",
    "ledger_interrupt",
    "checkpoint_corruption",
    "reflection_interrupt",
    "lesson_interrupt",
    "kill_switch",
    "restart_recovery",
    "qualification_blocks",
)

# Recoverable injections for the integrated fault session.
SCALE_SESSION_INJECTIONS: tuple[str, ...] = (
    "groq_429",
    "sambanova_429",
    "provider_timeout",
    "provider_invalid_schema",
    "stale_market_data",
    "missing_market_data",
    "duplicate_candidate",
    "duplicate_order_intent",
    "ledger_lock_contention",
    "interrupted_ledger_append",
    "snapshot_corruption",
    "missing_latest_snapshot",
    "disk_soft_limit",
    "network_loss",
    "partial_fill_before_crash",
    "filled_order_before_snapshot",
    "exit_event_before_position_snapshot",
    "reflection_interruption",
    "lesson_storage_interruption",
    "pause_during_pending_intent",
    "process_termination",
)

SCALE_TERMINAL_INJECTIONS: tuple[str, ...] = (
    "clock_jump_forward",
    "clock_jump_backward",
    "disk_hard_limit",
    "kill_switch_during_open_position",
)

SCALE_LOCAL_PROBES: tuple[str, ...] = (
    "cancel_replace_probe",
    "qualification_blocks_probe",
    "ledger_corruption_probe",
    "snapshot_corruption_probe",
    "restart_recovery_probe",
    "closed_loop_restart_probe",
    "closed_loop_interrupt_probe",
)

FAULT_CLASS_TO_COVERAGE: dict[str, tuple[str, ...]] = {
    "multi_symbol": ("universe_symbols",),
    "multi_regime": ("universe_vol_regimes",),
    "provider_outage": (
        "groq_429",
        "sambanova_429",
        "provider_timeout",
        "provider_invalid_schema",
        "network_loss",
        "closed_loop_provider_outage",
    ),
    "partial_fills": ("partial_fill_before_crash", "closed_loop_partial_fill"),
    "cancel_replace": ("cancel_replace_probe",),
    "clock_rollback": ("clock_jump_backward", "clock_jump_forward"),
    "disk_pressure": ("disk_soft_limit", "disk_hard_limit"),
    "ledger_interrupt": (
        "interrupted_ledger_append",
        "ledger_lock_contention",
        "ledger_corruption_probe",
    ),
    "checkpoint_corruption": (
        "snapshot_corruption",
        "missing_latest_snapshot",
        "snapshot_corruption_probe",
    ),
    "reflection_interrupt": ("reflection_interruption", "closed_loop_interrupt_probe"),
    "lesson_interrupt": ("lesson_storage_interruption", "closed_loop_interrupt_probe"),
    "kill_switch": ("kill_switch_during_open_position",),
    "restart_recovery": ("process_termination", "restart_recovery_probe", "closed_loop_restart_probe"),
    "qualification_blocks": ("qualification_blocks_probe",),
}


def injection_matrix() -> dict[str, object]:
    return {
        "schema": "v13_g_closed_loop_scale_injection_matrix",
        "fault_classes": list(SCALE_FAULT_CLASSES),
        "fault_class_to_coverage": {k: list(v) for k, v in FAULT_CLASS_TO_COVERAGE.items()},
        "session_injections": list(SCALE_SESSION_INJECTIONS),
        "terminal_injections": list(SCALE_TERMINAL_INJECTIONS),
        "local_probes": list(SCALE_LOCAL_PROBES),
    }


__all__ = [
    "FAULT_CLASS_TO_COVERAGE",
    "SCALE_FAULT_CLASSES",
    "SCALE_LOCAL_PROBES",
    "SCALE_SESSION_INJECTIONS",
    "SCALE_TERMINAL_INJECTIONS",
    "injection_matrix",
]
