"""Build founder-only demo monitor display payload (V18.2.25)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_founder_demo_monitor.constants import (
    LANE,
    LANE_LABEL_CANARY,
    LANE_LABEL_RESEARCH,
    LANE_NAME,
    SCHEMA_ID,
)
from backend.nexus_founder_demo_monitor.loader import load_raw_monitor_feed
from backend.nexus_founder_demo_monitor.sanitize import strip_forbidden_keys


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mask_demo_uid(uid: str | None) -> str | None:
    if uid is None:
        return None
    s = str(uid).strip()
    if not s:
        return None
    if len(s) <= 4:
        return "*" * len(s)
    if len(s) <= 6:
        return s[:1] + ("*" * (len(s) - 2)) + s[-1:]
    return s[:3] + ("*" * max(3, len(s) - 6)) + s[-3:]


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _empty_position() -> dict[str, Any]:
    return {
        "open": False,
        "symbol": None,
        "side": None,
        "notional": None,
        "entry": None,
        "current": None,
        "stop": None,
        "target": None,
        "unrealized_pnl": None,
        "expected_net_target": None,
        "expected_time_to_target": None,
        "strategy_horizon": None,
        "hold_duration": None,
        "mfe": None,
        "mae": None,
    }


def _empty_accounting() -> dict[str, Any]:
    return {
        "last_exit_reason": None,
        "exchange_closed_pnl": None,
        "fees": None,
        "calculated_net": None,
        "wallet_delta": None,
        "wallet_reconciliation_status": None,
        "process_class": None,
        "pnl_provenance": None,
    }


def _lane_label(raw: dict[str, Any]) -> str:
    explicit = raw.get("lane_label") or raw.get("process_lane") or raw.get("lifecycle_purpose")
    if explicit:
        s = str(explicit).upper()
        if "CANARY" in s or "TRANSPORT" in s:
            return LANE_LABEL_CANARY
        if "RESEARCH" in s or "PNL" in s:
            return LANE_LABEL_RESEARCH
    lanes = raw.get("execution_lanes")
    if isinstance(lanes, dict):
        active = str(lanes.get("active_lane") or "").upper()
        if "SHADOW" in active or "CANARY" in active:
            return LANE_LABEL_CANARY
        if "REAL" in active or "BYBIT" in active:
            return LANE_LABEL_RESEARCH
    purpose = str(raw.get("execution_purpose") or raw.get("lifecycle_purpose") or "").upper()
    if "CANARY" in purpose:
        return LANE_LABEL_CANARY
    return LANE_LABEL_RESEARCH


def _map_active_position(raw: dict[str, Any]) -> dict[str, Any]:
    pos = _empty_position()
    candidates = raw.get("active_position") or raw.get("current_real_position") or raw.get(
        "current_real_positions"
    )
    item: dict[str, Any] | None = None
    if isinstance(candidates, dict) and candidates:
        item = candidates
    elif isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict):
            item = first

    if not item:
        # Some feeds nest open fields at top level.
        if raw.get("symbol") and (raw.get("entry") or raw.get("entry_price")) and not raw.get(
            "exit"
        ):
            item = raw
        else:
            return pos

    qty = _num(item.get("qty") or item.get("size") or item.get("position_qty"))
    entry = _num(item.get("entry") or item.get("entry_price") or item.get("avgPrice"))
    notional = _num(item.get("notional") or item.get("position_notional"))
    if notional is None and qty is not None and entry is not None:
        notional = abs(qty * entry)

    pos.update(
        {
            "open": True,
            "symbol": _str_or_none(item.get("symbol")),
            "side": _str_or_none(item.get("side")),
            "notional": notional,
            "entry": entry,
            "current": _num(item.get("current") or item.get("mark_price") or item.get("markPrice")),
            "stop": _num(item.get("stop") or item.get("stop_loss") or item.get("sl")),
            "target": _num(item.get("target") or item.get("tp") or item.get("take_profit")),
            "unrealized_pnl": _num(
                item.get("unrealized_pnl") or item.get("unrealisedPnl") or item.get("upnl")
            ),
            "expected_net_target": _num(
                item.get("expected_net_target") or item.get("expected_target_net_pnl")
            ),
            "expected_time_to_target": _str_or_none(
                item.get("expected_time_to_target") or item.get("eta_to_target")
            ),
            "strategy_horizon": _str_or_none(
                item.get("strategy_horizon") or item.get("horizon")
            ),
            "hold_duration": _str_or_none(
                item.get("hold_duration") or item.get("hold_sec") or item.get("hold_seconds")
            ),
            "mfe": _num(item.get("mfe") or item.get("MFE")),
            "mae": _num(item.get("mae") or item.get("MAE")),
        }
    )
    return pos


def _map_accounting(raw: dict[str, Any]) -> dict[str, Any]:
    acct = _empty_accounting()
    life = raw.get("last_lifecycle")
    if not isinstance(life, dict):
        life = {}

    wallet_block = raw.get("_wallet_block") if isinstance(raw.get("_wallet_block"), dict) else {}
    compact = wallet_block.get("compact") if isinstance(wallet_block, dict) else None
    last_wallet: dict[str, Any] = {}
    if isinstance(compact, list) and compact and isinstance(compact[0], dict):
        last_wallet = compact[0]

    pnl_block = raw.get("_pnl_provenance") if isinstance(raw.get("_pnl_provenance"), dict) else {}
    session = pnl_block.get("session") if isinstance(pnl_block, dict) else None
    last_pnl: dict[str, Any] = {}
    if isinstance(session, list) and session and isinstance(session[0], dict):
        last_pnl = session[0]

    realized = _num(
        life.get("realized_pnl")
        or life.get("exchange_closed_pnl")
        or last_wallet.get("delta")
    )
    fees = _num(life.get("fees") or last_wallet.get("fees"))
    wallet_delta = _num(life.get("wallet_delta") or last_wallet.get("delta"))
    calculated_net = _num(life.get("calculated_net"))
    if calculated_net is None and realized is not None and fees is not None:
        # Prefer exchange realized; if realized already net of fees, keep as-is.
        calculated_net = realized

    acct.update(
        {
            "last_exit_reason": _str_or_none(
                life.get("exit_reason")
                or life.get("exit_reason_from_lifecycle")
                or raw.get("last_exit_reason")
            ),
            "exchange_closed_pnl": realized,
            "fees": fees,
            "calculated_net": calculated_net,
            "wallet_delta": wallet_delta,
            "wallet_reconciliation_status": _str_or_none(
                life.get("wallet_recon_status")
                or last_wallet.get("status")
                or raw.get("wallet_reconciliation_status")
            ),
            "process_class": _str_or_none(
                life.get("process_class") or last_pnl.get("process_class")
            ),
            "pnl_provenance": _str_or_none(
                life.get("pnl_provenance") or last_pnl.get("provenance")
            ),
        }
    )

    # Enrich MFE/MAE from last lifecycle when flat.
    return acct


def _map_wallet(raw: dict[str, Any]) -> dict[str, Any]:
    equity = _num(raw.get("equity") or raw.get("wallet_equity"))
    balance = _num(raw.get("wallet_balance") or raw.get("available_balance"))
    delta = _num(raw.get("wallet_delta") or raw.get("equity_delta"))
    if delta is None:
        life = raw.get("last_lifecycle")
        if isinstance(life, dict):
            delta = _num(life.get("wallet_delta"))
    if delta is None:
        wb = raw.get("_wallet_block")
        if isinstance(wb, dict):
            compact = wb.get("compact")
            if isinstance(compact, list) and compact and isinstance(compact[0], dict):
                delta = _num(compact[0].get("delta"))

    return {
        "equity": equity,
        "wallet_balance": balance,
        "available_balance": _num(raw.get("available_balance")),
        "delta": delta,
        "settle_coin": _str_or_none(raw.get("settle_coin")) or "USDT",
        "demo_account_type": _str_or_none(raw.get("demo_account_type") or raw.get("wallet_type")),
    }


def _fail_closed_empty(*, status: str, note: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "ok": True,
        "lane": LANE,
        "laneName": LANE_NAME,
        "founderOnly": True,
        "memberAccessible": False,
        "mainnet": False,
        "real_money": False,
        "member_execution": 0,
        "feed_ready": False,
        "feed_status": status,
        "feed_source": None,
        "generatedAt": _utc(),
        "demo_uid_masked": None,
        "lane_label": None,
        "wallet": {
            "equity": None,
            "wallet_balance": None,
            "available_balance": None,
            "delta": None,
            "settle_coin": None,
            "demo_account_type": None,
        },
        "active_position": _empty_position(),
        "mfe": None,
        "mae": None,
        "accounting": _empty_accounting(),
        "display": {
            "live_position": False,
            "wallet": False,
            "MFE_MAE": False,
            "accounting_visible": False,
        },
        "note": note,
    }


def build_founder_demo_monitor_snapshot(
    *,
    actor_tier: str,
    identity_source: str,
) -> dict[str, Any]:
    raw, source, status = load_raw_monitor_feed()

    # Directive: if Agent B campaign core feed not ready, fail-closed empty honestly.
    # FEED_STALE_CORE (v23/v24) is treated as not-ready for live campaign display.
    if raw is None or status in ("FEED_UNAVAILABLE", "FEED_UNPARSEABLE", "FEED_STALE_CORE"):
        note = {
            "FEED_UNAVAILABLE": (
                "Founder demo-monitor feed unavailable — Agent B campaign core/monitor "
                "not mounted. Fail-closed empty state; no fabricated values."
            ),
            "FEED_UNPARSEABLE": (
                "Founder demo-monitor feed unparseable — fail-closed empty state."
            ),
            "FEED_STALE_CORE": (
                "Agent B v18.2.25 core/monitor campaign feed not ready "
                f"(stale source={source}). Fail-closed empty state; contract wired."
            ),
        }.get(
            status,
            "Founder demo-monitor fail-closed empty state.",
        )
        payload = _fail_closed_empty(status=status, note=note)
        payload["actor"] = {"tier": actor_tier, "identitySource": identity_source}
        if source:
            payload["feed_source_stale"] = source
        return payload

    # FEED_READY — map honestly from Agent B payload.
    wallet = _map_wallet(raw)
    position = _map_active_position(raw)
    accounting = _map_accounting(raw)

    mfe = position.get("mfe")
    mae = position.get("mae")
    if mfe is None:
        mfe = _num(raw.get("mfe") or raw.get("MFE"))
    if mae is None:
        mae = _num(raw.get("mae") or raw.get("MAE"))
    life = raw.get("last_lifecycle")
    if isinstance(life, dict):
        if mfe is None:
            mfe = _num(life.get("mfe") or life.get("MFE"))
        if mae is None:
            mae = _num(life.get("mae") or life.get("MAE"))
        if not accounting.get("last_exit_reason"):
            accounting["last_exit_reason"] = _str_or_none(
                life.get("exit_reason") or life.get("exit_reason_from_lifecycle")
            )
        # When flat, surface last-lifecycle hold / horizon on accounting side only.
        if not position["open"]:
            if position.get("hold_duration") is None:
                position["hold_duration"] = _str_or_none(
                    life.get("hold_duration") or life.get("hold_sec")
                )
            if position.get("strategy_horizon") is None:
                position["strategy_horizon"] = _str_or_none(life.get("strategy_horizon"))
            if position.get("expected_net_target") is None:
                position["expected_net_target"] = _num(
                    life.get("expected_net_target") or life.get("expected_target_net_pnl")
                )
            if position.get("expected_time_to_target") is None:
                position["expected_time_to_target"] = _str_or_none(
                    life.get("expected_time_to_target")
                )

    uid = _str_or_none(raw.get("demo_uid") or raw.get("account_uid") or raw.get("uid"))
    lane_label = _lane_label(raw)

    display = {
        "live_position": bool(position.get("open")),
        "wallet": wallet.get("equity") is not None or wallet.get("wallet_balance") is not None,
        "MFE_MAE": mfe is not None or mae is not None,
        "accounting_visible": any(
            accounting.get(k) is not None
            for k in (
                "last_exit_reason",
                "exchange_closed_pnl",
                "fees",
                "calculated_net",
                "wallet_delta",
                "wallet_reconciliation_status",
            )
        ),
    }

    payload: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "ok": True,
        "lane": LANE,
        "laneName": LANE_NAME,
        "founderOnly": True,
        "memberAccessible": False,
        "mainnet": False,
        "real_money": False,
        "member_execution": 0,
        "feed_ready": True,
        "feed_status": status,
        "feed_source": source,
        "generatedAt": _utc(),
        "actor": {"tier": actor_tier, "identitySource": identity_source},
        "demo_uid_masked": mask_demo_uid(uid),
        "lane_label": lane_label,
        "wallet": wallet,
        "active_position": position,
        "mfe": mfe,
        "mae": mae,
        "accounting": accounting,
        "display": display,
        "note": (
            "Founder-only real demo monitor — RESEARCH vs CANARY labeled; "
            "members inaccessible; no fabricated accounting."
        ),
    }
    return strip_forbidden_keys(payload)
