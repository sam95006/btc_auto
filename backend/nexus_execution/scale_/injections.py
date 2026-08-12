"""V10 Lane B injection catalog for execution + session scale.

Maps Founder-required fault classes onto Session Orchestrator V1.1 injection
flags (and scale-local post-run probes for ledger/snapshot corruption).
"""
from __future__ import annotations

# Required Founder fault classes → concrete injection flags / probes.
SCALE_FAULT_CLASSES: tuple[str, ...] = (
    "process_crashes",
    "partial_fills",
    "duplicate_intents",
    "clock_jumps",
    "provider_outages",
    "storage_limits",
    "ledger_corruption",
    "snapshot_corruption",
)

# Long-running 30d/90d sessions: recoverable / absorbable injections only.
# Terminal clock-jump / hard-disk / kill-switch cases run as focused probes.
SCALE_LONG_SESSION_INJECTIONS: tuple[str, ...] = (
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

# Focused probes that must fail-closed (BLOCKED / BLOCKED_AMBIGUOUS / FAILED_SAFE).
FOCUSED_TERMINAL_INJECTIONS: tuple[str, ...] = (
    "clock_jump_forward",
    "clock_jump_backward",
    "disk_hard_limit",
)

# Union catalog used for readiness reporting.
SCALE_INJECTION_CATALOG: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *SCALE_LONG_SESSION_INJECTIONS,
            *FOCUSED_TERMINAL_INJECTIONS,
            # Scale-local probes (not Session catalog flags; applied post-run).
            "ledger_corruption_probe",
            "snapshot_corruption_probe",
        )
    )
)

FAULT_CLASS_TO_INJECTIONS: dict[str, tuple[str, ...]] = {
    "process_crashes": ("process_termination", "partial_fill_before_crash"),
    "partial_fills": ("partial_fill_before_crash",),
    "duplicate_intents": ("duplicate_order_intent", "duplicate_candidate"),
    "clock_jumps": ("clock_jump_forward", "clock_jump_backward"),
    "provider_outages": (
        "groq_429",
        "sambanova_429",
        "provider_timeout",
        "provider_invalid_schema",
        "network_loss",
    ),
    "storage_limits": ("disk_soft_limit", "disk_hard_limit"),
    "ledger_corruption": (
        "interrupted_ledger_append",
        "ledger_lock_contention",
        "ledger_corruption_probe",
    ),
    "snapshot_corruption": (
        "snapshot_corruption",
        "missing_latest_snapshot",
        "snapshot_corruption_probe",
    ),
}


def injection_matrix() -> dict[str, object]:
    return {
        "schema": "v10_execution_session_scale_injection_matrix",
        "fault_classes": list(SCALE_FAULT_CLASSES),
        "fault_class_to_injections": {
            k: list(v) for k, v in FAULT_CLASS_TO_INJECTIONS.items()
        },
        "long_session_injections": list(SCALE_LONG_SESSION_INJECTIONS),
        "focused_terminal_injections": list(FOCUSED_TERMINAL_INJECTIONS),
        "catalog": list(SCALE_INJECTION_CATALOG),
    }


__all__ = [
    "FAULT_CLASS_TO_INJECTIONS",
    "FOCUSED_TERMINAL_INJECTIONS",
    "SCALE_FAULT_CLASSES",
    "SCALE_INJECTION_CATALOG",
    "SCALE_LONG_SESSION_INJECTIONS",
    "injection_matrix",
]
