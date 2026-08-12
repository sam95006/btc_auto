"""Bounded post-stop finalization poll — no -1 sentinels; UNKNOWN ≠ MISMATCH."""
from __future__ import annotations

import time
from typing import Any, Callable

from backend.nexus_demo_execution.count_semantics import (
    classify_account_flat,
    count_or_none,
    reconcile_flat,
)

TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "KILLED"})


def extract_account_counts(account: dict[str, Any] | None) -> tuple[int | None, int | None, str | None]:
    """Parse account payload. Zero is valid. Missing/error → None + reason."""
    if not isinstance(account, dict):
        return None, None, "account_payload_missing"
    if account.get("_error") or account.get("_http_error"):
        return None, None, str(account.get("detail") or account.get("body_head") or "account_api_failure")[:200]
    # Prefer explicit count fields; never coerce with `or -1`.
    if "open_positions" in account:
        pos = count_or_none(account.get("open_positions"))
    elif "position_count" in account:
        pos = count_or_none(account.get("position_count"))
    else:
        pos = None
    if "open_orders" in account:
        ord_ = count_or_none(account.get("open_orders"))
    elif "open_order_count" in account:
        ord_ = count_or_none(account.get("open_order_count"))
    else:
        ord_ = None
    reason = None
    if pos is None or ord_ is None:
        reason = "account_counts_unavailable"
    return pos, ord_, reason


def is_stable_post_stop(session: dict[str, Any], account: dict[str, Any] | None) -> bool:
    status = str(session.get("status") or session.get("session_status") or "").upper()
    if status not in TERMINAL_STATUSES:
        return False
    if bool(session.get("thread_alive")):
        return False
    if bool(session.get("session_write_enabled") or session.get("session_write_window_open") or session.get("smoke_write_window_open")):
        return False
    if bool(session.get("effective_demo_write_authorized")):
        return False
    pos, ord_, _ = extract_account_counts(account)
    return reconcile_flat(pos, ord_) == "MATCH"


def poll_until_stable(
    *,
    fetch_session: Callable[[], dict[str, Any]],
    fetch_account: Callable[[], dict[str, Any]],
    timeout_sec: float = 90.0,
    interval_sec: float = 2.0,
    ignore_stale_stop: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Poll session + account until terminal-flat or timeout.

    On timeout: counts null, reconciliation UNKNOWN (never -1 / never forced MISMATCH).
    """
    deadline = time.time() + max(1.0, timeout_sec)
    last_session: dict[str, Any] = {}
    last_account: dict[str, Any] = {}
    polls = 0
    while time.time() < deadline:
        polls += 1
        last_session = fetch_session() or {}
        last_account = fetch_account() or {}
        if ignore_stale_stop and ignore_stale_stop(last_session):
            time.sleep(interval_sec)
            continue
        if is_stable_post_stop(last_session, last_account):
            pos, ord_, _ = extract_account_counts(last_account)
            return {
                "finalization_status": "STABLE",
                "session_status": str(last_session.get("status") or last_session.get("session_status") or ""),
                "thread_alive": bool(last_session.get("thread_alive")),
                "session_write_window_open": bool(
                    last_session.get("session_write_enabled")
                    or last_session.get("session_write_window_open")
                    or last_session.get("smoke_write_window_open")
                ),
                "effective_demo_write_authorized": bool(last_session.get("effective_demo_write_authorized")),
                "position_count_final": pos,
                "open_order_count_final": ord_,
                "reconciliation_final": "MATCH",
                "account_classification": classify_account_flat(pos, ord_),
                "polls": polls,
                "session": last_session,
                "account": last_account,
            }
        time.sleep(interval_sec)

    pos, ord_, reason = extract_account_counts(last_account)
    status = str(last_session.get("status") or last_session.get("session_status") or "")
    recon = reconcile_flat(pos, ord_)
    # Timeout ⇒ UNKNOWN finalization; do not invent MISMATCH from missing data.
    if pos is None or ord_ is None:
        recon = "UNKNOWN"
    return {
        "finalization_status": "UNKNOWN",
        "session_status": status,
        "thread_alive": bool(last_session.get("thread_alive")),
        "session_write_window_open": bool(
            last_session.get("session_write_enabled")
            or last_session.get("session_write_window_open")
            or last_session.get("smoke_write_window_open")
        ),
        "effective_demo_write_authorized": bool(last_session.get("effective_demo_write_authorized")),
        "position_count_final": pos,
        "open_order_count_final": ord_,
        "reconciliation_final": recon if recon != "MISMATCH" or (pos is not None and ord_ is not None) else "UNKNOWN",
        "account_classification": classify_account_flat(pos, ord_),
        "timeout_reason": reason or "finalization_poll_timeout",
        "polls": polls,
        "session": last_session,
        "account": last_account,
    }


def build_final_snapshot(
    *,
    session_snap: dict[str, Any],
    poll_result: dict[str, Any],
    stop_reason: str = "DEADLINE_FINALIZE",
    stop_http: Any = None,
    stop_response: Any = None,
) -> dict[str, Any]:
    pos = poll_result.get("position_count_final")
    ord_ = poll_result.get("open_order_count_final")
    # Hard rule: never emit -1.
    if pos is not None and int(pos) < 0:
        pos = None
    if ord_ is not None and int(ord_) < 0:
        ord_ = None
    recon = poll_result.get("reconciliation_final") or reconcile_flat(
        count_or_none(pos), count_or_none(ord_)
    )
    return {
        **session_snap,
        "stop_reason": stop_reason,
        "stop_http": stop_http,
        "stop_response_head": stop_response if isinstance(stop_response, dict) else {"raw": str(stop_response)[:400]},
        "finalization_status": poll_result.get("finalization_status"),
        "position_count_final": pos,
        "open_order_count_final": ord_,
        "reconciliation_final": recon,
        "account_classification": poll_result.get("account_classification"),
        "thread_alive_after_finalize": bool(poll_result.get("thread_alive")),
        "session_write_window_open": bool(poll_result.get("session_write_window_open")),
        "effective_demo_write_authorized": bool(poll_result.get("effective_demo_write_authorized")),
        "finalization_polls": poll_result.get("polls"),
        "timeout_reason": poll_result.get("timeout_reason"),
    }
