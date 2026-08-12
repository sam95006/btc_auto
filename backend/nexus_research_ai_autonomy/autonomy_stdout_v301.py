"""V30.1 free-log stdout observability for ResearchAutonomyService.

Stdout is observability only — not canonical evidence. Never log credentials.
"""

from __future__ import annotations

import re
from typing import Any

_PREFIX = "[NEXUS-AUTONOMY]"
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|api[_-]?secret|secret|password|token|credential|authorization)",
    re.I,
)
_SECRET_VALUE_RE = re.compile(r"^[A-Za-z0-9_\-]{20,}$")

_SAFE_ENUM_ALLOWLIST = {
    "GLOBAL_PENDING_ACCOUNTING",
    "PRIOR_ACCOUNTING_INCOMPLETE",
    "PRIOR_REFLECTION_INCOMPLETE",
    "SAME_SETUP_REPEAT_BLOCKED",
    "SAME_SETUP_REENTRY_BLOCKED",
    "PENDING_WALLET_RECONCILIATION",
    "NO_DIRECTIONAL_CANDIDATE",
}


def _safe(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).strip()
    if not text:
        return "null"
    lowered = text.lower()
    if _SECRET_KEY_RE.search(lowered):
        return "<redacted>"
    if text in _SAFE_ENUM_ALLOWLIST:
        # These are intentionally human-readable status enums.
        # They must bypass the secret-value regex used for other redactions.
        return text
    if len(text) >= 24 and _SECRET_VALUE_RE.match(text) and not text.isdigit():
        return "<redacted>"
    if "api_key" in lowered or "api_secret" in lowered:
        return "<redacted>"
    return text.replace("\n", " ")[:200]


def _emit(header: str, fields: dict[str, Any]) -> None:
    print(f"{_PREFIX} {header}", flush=True)
    for key, value in fields.items():
        print(f"{key}={_safe(value)}", flush=True)


def log_boot(
    *,
    runtime: str,
    boot_ready: bool,
    exchange: str,
    worker_id: str,
) -> None:
    _emit(
        "BOOT",
        {
            "runtime": runtime,
            "boot_ready": boot_ready,
            "exchange": exchange,
            "worker": worker_id,
        },
    )


def log_cycle(
    *,
    cycle_n: int,
    started: str | None,
    completed: str | None,
    status: str,
    duration: float | None,
    position: str,
    market_scan_complete: bool | None,
    candidate_count: int | None,
    wait_reason: str | None,
    next_cycle: str | None,
    last_flat_scan_candidate_count: int | None = None,
    last_flat_scan_at: str | None = None,
) -> None:
    _emit(
        "CYCLE",
        {
            "n": cycle_n,
            "started": started,
            "completed": completed,
            "status": status,
            "duration": f"{duration:.3f}" if duration is not None else None,
            "position": position,
            "market_scan_complete": market_scan_complete,
            "candidate_count": candidate_count,
            "last_flat_scan_candidate_count": last_flat_scan_candidate_count,
            "last_flat_scan_at": last_flat_scan_at,
            "wait_reason": wait_reason,
            "next_cycle": next_cycle,
        },
    )


def log_manage(
    *,
    symbol: str | None,
    side: str | None,
    status: str,
    mfe: Any = None,
    mae: Any = None,
    entry_price: Any = None,
    current_price: Any = None,
    hold_sec: Any = None,
    stop_price: Any = None,
    take_profit_price: Any = None,
    trail_state: Any = None,
    adaptive_action: str | None,
    exit_reason: str | None = None,
    next_poll: str | None,
) -> None:
    _emit(
        "MANAGE",
        {
            "symbol": symbol,
            "side": side,
            "status": status,
            "MFE": mfe,
            "MAE": mae,
            "entry_price": entry_price,
            "current_price": current_price,
            "hold_sec": hold_sec,
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
            "trail_state": trail_state,
            "adaptive_action": adaptive_action,
            "exit_reason": exit_reason,
            "next_poll": next_poll,
        },
    )


def log_error(
    *,
    cycle: int,
    error_class: str,
    service_status: str,
    next_retry: str | None,
    error_detail: str | None = None,
) -> None:
    fields = {
        "cycle": cycle,
        "error_class": error_class,
        "service_status": service_status,
        "next_retry": next_retry,
    }
    if error_detail:
        fields["error_detail"] = error_detail
    _emit("ERROR", fields)


def log_order(
    *,
    symbol: str | None,
    side: str | None,
    demo: bool,
    notional: Any,
    result: str,
) -> None:
    _emit(
        "ORDER",
        {
            "symbol": symbol,
            "side": side,
            "demo": demo,
            "notional": notional,
            "result": result,
        },
    )


def log_trade_complete(
    *,
    symbol: str | None,
    side: str | None,
    net_realized: Any,
    exit_reason: str | None,
    wallet_reconciliation: Any,
) -> None:
    _emit(
        "TRADE_COMPLETE",
        {
            "symbol": symbol,
            "side": side,
            "net_realized": net_realized,
            "exit_reason": exit_reason,
            "wallet_reconciliation": wallet_reconciliation,
        },
    )


def _lifecycle_from_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    life = result.get("lifecycle")
    if isinstance(life, dict):
        return life
    raw = result.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get("lifecycle"), dict):
        return raw["lifecycle"]
    return {}


def _extract_order_fields(result: dict[str, Any] | None) -> dict[str, Any]:
    life = _lifecycle_from_result(result)
    preflight = (result or {}).get("exchange_preflight") or life.get("exchange_preflight") or {}
    if not isinstance(preflight, dict):
        preflight = {}
    selection = (result or {}).get("two_sided_selection") or {}
    if isinstance(selection, dict):
        sel = selection.get("selection") or selection
        if isinstance(sel, dict):
            symbol = sel.get("selected_symbol") or sel.get("symbol")
            side = sel.get("selected_side") or sel.get("side")
        else:
            symbol = side = None
    else:
        symbol = side = None
    symbol = life.get("symbol") or symbol or (result or {}).get("symbol")
    side = life.get("side") or side or (result or {}).get("side")
    notional = (
        life.get("notional_usdt")
        or preflight.get("notional_usdt")
        or (life.get("exact_pnl_accounting") or {}).get("notional_usdt")
    )
    accepted = bool((result or {}).get("executed"))
    order_result = "ACCEPTED" if accepted else "REJECTED"
    if (result or {}).get("reason"):
        order_result = f"{order_result}:{(result or {}).get('reason')}"
    return {
        "symbol": symbol,
        "side": side,
        "notional": notional,
        "result": order_result,
    }


def _extract_manage_fields(
    *,
    result: dict[str, Any] | None,
    reconcile: dict[str, Any] | None,
    next_cycle: str | None,
) -> dict[str, Any]:
    recon = reconcile if isinstance(reconcile, dict) else {}
    symbol = recon.get("symbol")
    side = recon.get("side")
    pos = recon.get("position")
    if isinstance(pos, dict):
        symbol = symbol or pos.get("symbol")
        side = side or pos.get("side")

    mfe = mae = None
    entry_price = current_price = hold_sec = None
    stop_price = take_profit_price = trail_state = None
    exit_reason = None
    adaptive_action = (result or {}).get("action")
    tick_detail = (result or {}).get("tick_detail")
    if isinstance(tick_detail, list) and tick_detail:
        for tick in reversed(tick_detail):
            if not isinstance(tick, dict):
                continue
            adaptive_action = tick.get("adaptive_action") or tick.get("action") or adaptive_action
            if exit_reason is None:
                exit_reason = tick.get("exit_reason") or tick.get("close_error")
            tel = tick.get("open_position_telemetry")
            if isinstance(tel, dict):
                mfe = tel.get("mfe_usdt")
                mae = tel.get("mae_usdt")
                symbol = symbol or tel.get("symbol")
                side = side or tel.get("side")
                entry_price = tel.get("entry_price") if entry_price is None else entry_price
                current_price = tel.get("current_price") if current_price is None else current_price
                hold_sec = tel.get("hold_sec") if hold_sec is None else hold_sec
                stop_price = tel.get("stop_price") if stop_price is None else stop_price
                take_profit_price = (
                    tel.get("take_profit_price") if take_profit_price is None else take_profit_price
                )
                trail_state = tel.get("trail_state") if trail_state is None else trail_state
                break

    return {
        "symbol": symbol,
        "side": side,
        "mfe": mfe,
        "mae": mae,
        "entry_price": entry_price,
        "current_price": current_price,
        "hold_sec": hold_sec,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "trail_state": trail_state,
        "adaptive_action": adaptive_action,
        "exit_reason": exit_reason,
        "next_poll": next_cycle,
    }


def _extract_trade_complete_fields(result: dict[str, Any] | None) -> dict[str, Any]:
    life = _lifecycle_from_result(result)
    if not life and isinstance(result, dict):
        # Manage close may embed lifecycle on last tick
        tick_detail = result.get("tick_detail")
        if isinstance(tick_detail, list) and tick_detail:
            last_tick = tick_detail[-1]
            if isinstance(last_tick, dict):
                life = last_tick.get("lifecycle") or last_tick.get("closed_lifecycle") or {}
                if not life:
                    life = {
                        "symbol": last_tick.get("symbol"),
                        "side": last_tick.get("side"),
                        "exit_reason": last_tick.get("exit_reason") or last_tick.get("reason"),
                        "exact_pnl_accounting": last_tick.get("exact_pnl_accounting"),
                        "wallet_reconciliation": last_tick.get("wallet_reconciliation"),
                    }

    ea = life.get("exact_pnl_accounting") or {}
    wr = life.get("wallet_reconciliation") or {}
    net = (
        ea.get("calculated_net_pnl")
        or ea.get("net_realized")
        or life.get("net_realized")
        or life.get("net_pnl")
    )
    wr_pass = wr.get("WALLET_RECONCILIATION_PASS")
    if wr_pass is None:
        wr_status = wr.get("status") or ("PASS" if wr else None)
    else:
        wr_status = "PASS" if wr_pass else "FAIL"
    return {
        "symbol": life.get("symbol"),
        "side": life.get("side"),
        "net_realized": net,
        "exit_reason": life.get("exit_reason") or (result or {}).get("reason"),
        "wallet_reconciliation": wr_status,
    }


def observe_completed_tick(
    *,
    cycle_n: int,
    last: dict[str, Any],
    health: Any,
) -> None:
    """Emit stdout observability for one completed autonomy tick."""
    status = str(last.get("service_status") or getattr(health, "service_status", "UNKNOWN"))
    result = last.get("result") if isinstance(last.get("result"), dict) else {}
    reconcile = last.get("reconcile") if isinstance(last.get("reconcile"), dict) else {}

    started = getattr(health, "last_cycle_started_at", None)
    completed = getattr(health, "last_cycle_completed_at", None)
    next_cycle = getattr(health, "next_cycle_due_at", None)
    duration = last.get("duration_sec")
    if duration is None:
        duration = getattr(health, "last_cycle_duration_sec", None)

    position = "OPEN" if getattr(health, "open_position", False) else "FLAT"
    market_scan_complete = getattr(health, "market_scan_complete", None)
    candidate_count = getattr(health, "candidate_count", None)
    last_flat_scan_candidate_count = getattr(health, "last_flat_scan_candidate_count", None)
    last_flat_scan_at = getattr(health, "last_flat_scan_at", None)
    wait_reason = result.get("reason") if isinstance(result, dict) else None
    if not wait_reason and status == "WAITING_MARKET":
        reasons = getattr(health, "top_rejection_reasons", None)
        if isinstance(reasons, list) and reasons:
            wait_reason = reasons[0]

    log_cycle(
        cycle_n=cycle_n,
        started=started,
        completed=completed,
        status=status,
        duration=float(duration) if duration is not None else None,
        position=position,
        market_scan_complete=None if status == "MANAGING_POSITION" else market_scan_complete,
        candidate_count=None if status == "MANAGING_POSITION" else candidate_count,
        last_flat_scan_candidate_count=(
            last_flat_scan_candidate_count if status == "MANAGING_POSITION" else None
        ),
        last_flat_scan_at=(last_flat_scan_at if status == "MANAGING_POSITION" else None),
        wait_reason=wait_reason,
        next_cycle=next_cycle,
    )

    if status == "MANAGING_POSITION":
        manage_fields = _extract_manage_fields(
            result=result,
            reconcile=reconcile,
            next_cycle=next_cycle,
        )
        log_manage(
            symbol=manage_fields["symbol"],
            side=manage_fields["side"],
            status="MANAGING_POSITION",
            mfe=manage_fields["mfe"],
            mae=manage_fields["mae"],
            entry_price=manage_fields["entry_price"],
            current_price=manage_fields["current_price"],
            hold_sec=manage_fields["hold_sec"],
            stop_price=manage_fields["stop_price"],
            take_profit_price=manage_fields["take_profit_price"],
            trail_state=manage_fields["trail_state"],
            adaptive_action=manage_fields["adaptive_action"],
            exit_reason=manage_fields.get("exit_reason"),
            next_poll=manage_fields["next_poll"],
        )

    if last.get("error") or (status == "DEGRADED" and not last.get("ok", True)):
        error_class = str(
            last.get("error")
            or getattr(health, "degraded_reason", None)
            or result.get("reason")
            or "DEGRADED"
        )
        error_detail = None
        if isinstance(result, dict):
            error_detail = result.get("detail") or result.get("import_error_detail")
            if not error_detail and result.get("import_error_class"):
                error_detail = f"{result.get('import_error_class')}"
        log_error(
            cycle=cycle_n,
            error_class=error_class,
            service_status=status,
            next_retry=next_cycle,
            error_detail=error_detail,
        )

    if isinstance(result, dict) and result.get("executed"):
        order_fields = _extract_order_fields(result)
        log_order(
            symbol=order_fields["symbol"],
            side=order_fields["side"],
            demo=True,
            notional=order_fields["notional"],
            result=order_fields["result"],
        )

    if isinstance(result, dict) and result.get("closed"):
        trade_fields = _extract_trade_complete_fields(result)
        log_trade_complete(
            symbol=trade_fields["symbol"],
            side=trade_fields["side"],
            net_realized=trade_fields["net_realized"],
            exit_reason=trade_fields["exit_reason"],
            wallet_reconciliation=trade_fields["wallet_reconciliation"],
        )
