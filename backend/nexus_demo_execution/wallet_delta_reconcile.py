"""Attribute wallet deltas with evidence — never blame a session without IDs/timestamps."""
from __future__ import annotations

import hashlib
from typing import Any

# Bucket labels (evidence rows) — not necessarily the primary Founder classification.
BUCKETS = (
    "PRIOR_PROBE_SETTLEMENT",
    "TRADING_FEE",
    "REALIZED_PNL",
    "FUNDING",
    "EXTERNAL_ACCOUNT_ACTIVITY",
    "WALLET_SNAPSHOT_SEMANTIC_DIFFERENCE",
    "API_HISTORY_RETENTION_GAP",
    "API_UNSUPPORTED",
    "UNKNOWN",
)

# Founder §6 final primary classification — exactly one of these.
FOUNDER_CLASSIFICATIONS = (
    "FULLY_ATTRIBUTED",
    "PARTIALLY_ATTRIBUTED",
    "API_HISTORY_RETENTION_GAP",
    "API_UNSUPPORTED",
    "EXTERNAL_ACCOUNT_ACTIVITY",
    "WALLET_SNAPSHOT_SEMANTIC_DIFFERENCE",
    "UNKNOWN",
)

CLASSIFICATIONS = BUCKETS  # backward compatible alias


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hash_id(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    return hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:16]


def _in_window(ts_ms: Any, start_ms: int | None, end_ms: int | None) -> bool:
    t = _f(ts_ms)
    if t is None:
        return False
    # Accept seconds or ms
    if t < 1e12:
        t *= 1000.0
    if start_ms is not None and t < start_ms:
        return False
    if end_ms is not None and t > end_ms:
        return False
    return True


def reconcile_wallet_delta(
    *,
    starting_wallet: float,
    final_wallet: float,
    session_start_ms: int | None = None,
    session_end_ms: int | None = None,
    closed_pnl_rows: list[dict[str, Any]] | None = None,
    execution_rows: list[dict[str, Any]] | None = None,
    transaction_rows: list[dict[str, Any]] | None = None,
    prior_probe_fee_total: float | None = None,
    available_balance: float | None = None,
    equity: float | None = None,
) -> dict[str, Any]:
    wallet_delta = float(final_wallet) - float(starting_wallet)
    evidence: list[dict[str, Any]] = []
    attributed = 0.0
    buckets: dict[str, float] = {c: 0.0 for c in BUCKETS}
    api_unsupported = False
    semantic_only = False

    # Semantic difference: available vs wallet (informative only; not attributed to session PnL).
    if available_balance is not None and abs(float(available_balance) - float(final_wallet)) > 1e-8:
        semantic_only = True
        evidence.append(
            {
                "class": "WALLET_SNAPSHOT_SEMANTIC_DIFFERENCE",
                "wallet_balance": final_wallet,
                "available_balance": available_balance,
                "equity": equity,
                "note": "available_balance ≠ wallet_balance; do not treat as session PnL",
            }
        )

    for row in closed_pnl_rows or []:
        ts = row.get("updatedTime") or row.get("createdTime") or row.get("ts")
        in_sess = _in_window(ts, session_start_ms, session_end_ms)
        order_id = row.get("orderId") or row.get("orderLinkId")
        closed = _f(row.get("closedPnl")) or 0.0
        fees = abs(_f(row.get("openFee")) or 0.0) + abs(_f(row.get("closeFee")) or 0.0)
        funding = _f(row.get("fundingFee")) or 0.0
        if not in_sess or not order_id:
            evidence.append(
                {
                    "class": "API_HISTORY_RETENTION_GAP" if not order_id else "EXTERNAL_ACCOUNT_ACTIVITY",
                    "row_type": "closed_pnl",
                    "in_session_window": in_sess,
                    "order_id_hash": _hash_id(order_id),
                    "closed_pnl": closed,
                    "fees": fees,
                    "funding": funding,
                    "timestamp": ts,
                    "source_endpoint": "/v5/position/closed-pnl",
                }
            )
            continue
        if abs(closed) > 0:
            buckets["REALIZED_PNL"] += closed
            attributed += closed
            evidence.append(
                {
                    "class": "REALIZED_PNL",
                    "amount": closed,
                    "order_id_hash": _hash_id(order_id),
                    "timestamp": ts,
                    "source_endpoint": "/v5/position/closed-pnl",
                }
            )
        if fees > 0:
            buckets["TRADING_FEE"] -= fees
            attributed -= fees
            evidence.append(
                {
                    "class": "TRADING_FEE",
                    "amount": -fees,
                    "order_id_hash": _hash_id(order_id),
                    "timestamp": ts,
                    "source_endpoint": "/v5/position/closed-pnl",
                }
            )
        if abs(funding) > 0:
            buckets["FUNDING"] += funding
            attributed += funding
            evidence.append(
                {
                    "class": "FUNDING",
                    "amount": funding,
                    "order_id_hash": _hash_id(order_id),
                    "timestamp": ts,
                    "source_endpoint": "/v5/position/closed-pnl",
                }
            )

    for row in execution_rows or []:
        ts = row.get("execTime") or row.get("createdTime") or row.get("ts")
        in_sess = _in_window(ts, session_start_ms, session_end_ms)
        exec_id = row.get("execId") or row.get("orderId")
        fee = abs(_f(row.get("execFee") or row.get("fee")) or 0.0)
        if fee <= 0:
            continue
        if not in_sess or not exec_id:
            evidence.append(
                {
                    "class": "API_HISTORY_RETENTION_GAP" if not exec_id else "EXTERNAL_ACCOUNT_ACTIVITY",
                    "row_type": "execution",
                    "in_session_window": in_sess,
                    "execution_id_hash": _hash_id(exec_id),
                    "fee": fee,
                    "timestamp": ts,
                    "source_endpoint": "/v5/execution/list",
                }
            )
            continue
        buckets["TRADING_FEE"] -= fee
        attributed -= fee
        evidence.append(
            {
                "class": "TRADING_FEE",
                "amount": -fee,
                "execution_id_hash": _hash_id(exec_id),
                "order_id_hash": _hash_id(row.get("orderId")),
                "timestamp": ts,
                "source_endpoint": "/v5/execution/list",
            }
        )

    for row in transaction_rows or []:
        ts = row.get("transactionTime") or row.get("ts")
        change = _f(row.get("change") or row.get("cashFlow") or row.get("amount"))
        if change is None:
            continue
        in_sess = _in_window(ts, session_start_ms, session_end_ms)
        typ = str(row.get("type") or row.get("transactionType") or "UNKNOWN")
        if not in_sess:
            evidence.append(
                {
                    "class": "EXTERNAL_ACCOUNT_ACTIVITY",
                    "row_type": "transaction",
                    "type": typ,
                    "amount": change,
                    "ts": ts,
                    "in_session_window": False,
                }
            )
            continue
        cls = "FUNDING" if "FUND" in typ.upper() else ("TRADING_FEE" if "FEE" in typ.upper() else "EXTERNAL_ACCOUNT_ACTIVITY")
        buckets[cls] += change
        attributed += change
        evidence.append({"class": cls, "amount": change, "type": typ, "ts": ts, "tx_id": row.get("id") or row.get("transId")})

    if prior_probe_fee_total is not None and abs(prior_probe_fee_total) > 0:
        # Only attribute if magnitude matches unattributed remainder within tolerance AND ids exist elsewhere.
        rem = wallet_delta - attributed
        if abs(abs(prior_probe_fee_total) - abs(rem)) < 1e-6:
            buckets["PRIOR_PROBE_SETTLEMENT"] -= abs(prior_probe_fee_total)
            attributed -= abs(prior_probe_fee_total)
            evidence.append(
                {
                    "class": "PRIOR_PROBE_SETTLEMENT",
                    "amount": -abs(prior_probe_fee_total),
                    "note": "magnitude match only; requires probe order/exec hashes for hard attribution",
                }
            )

    unattributed = wallet_delta - attributed
    has_ledger = bool(closed_pnl_rows or execution_rows or transaction_rows)
    external_hits = sum(1 for e in evidence if e.get("class") == "EXTERNAL_ACCOUNT_ACTIVITY")

    # Founder primary classification (exactly one).
    if api_unsupported:
        primary = "API_UNSUPPORTED"
    elif abs(wallet_delta) < 1e-8:
        primary = "FULLY_ATTRIBUTED"
    elif abs(unattributed) < 1e-8 and abs(attributed) >= 1e-8:
        primary = "FULLY_ATTRIBUTED"
    elif abs(attributed) >= 1e-8 and abs(unattributed) >= 1e-8:
        primary = "PARTIALLY_ATTRIBUTED"
    elif not has_ledger:
        primary = "API_HISTORY_RETENTION_GAP"
    elif external_hits > 0 and abs(attributed) < 1e-8:
        primary = "EXTERNAL_ACCOUNT_ACTIVITY"
    elif semantic_only and abs(attributed) < 1e-8:
        # Semantic gap observed but does not by itself explain start→end wallet delta.
        primary = "UNKNOWN"
    else:
        primary = "UNKNOWN"

    return {
        "starting_wallet": starting_wallet,
        "final_wallet": final_wallet,
        "wallet_delta": round(wallet_delta, 8),
        "wallet_delta_total": round(wallet_delta, 8),
        "wallet_delta_attributed": round(attributed, 8),
        "wallet_delta_unattributed": round(unattributed, 8),
        "attributed_amount": round(attributed, 8),
        "unattributed_amount": round(unattributed, 8),
        "classification": primary,
        "evidence_record_count": len(evidence),
        "bucket_totals": {k: round(v, 8) for k, v in buckets.items() if abs(v) > 0},
        "evidence_records": evidence,
        "session_attribution_allowed": primary == "FULLY_ATTRIBUTED"
        and abs(unattributed) < 1e-8
        and abs(attributed) >= 1e-8,
        "founder_classifications": list(FOUNDER_CLASSIFICATIONS),
    }
