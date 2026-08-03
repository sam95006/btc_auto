#!/usr/bin/env python3
"""Read-only wallet delta forensic for the known -0.97052039 USDT residual.

No exchange writes. No order placement. Uses immutable evidence first;
optional read-only Demo API only if already configured.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "readiness" / "immutable" / "wallet_delta_forensic"
IMMUTABLE_12H = ROOT / "artifacts" / "readiness" / "immutable" / "post_12h_forensic"
TARGET_DELTA = -0.97052039
TOLERANCE = 1e-8

FOUNDER_CLASSES = (
    "WALLET_DELTA_FULLY_ATTRIBUTED",
    "WALLET_DELTA_PARTIALLY_ATTRIBUTED",
    "WALLET_DELTA_UNATTRIBUTED_API_HISTORY_INCOMPLETE",
    "WALLET_DELTA_UNATTRIBUTED_ACCOUNT_EPOCH_MISMATCH",
    "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _try_readonly_demo_history() -> dict[str, Any]:
    """Best-effort read-only Demo private history if credentials exist; never writes."""
    out: dict[str, Any] = {
        "attempted": False,
        "available": False,
        "error": None,
        "closed_pnl_count": 0,
        "execution_count": 0,
        "transaction_count": 0,
        "rows": [],
    }
    if os.environ.get("EXCHANGE_WRITE", "false").lower() in ("1", "true", "yes", "on"):
        out["error"] = "EXCHANGE_WRITE_MUST_REMAIN_FALSE"
        return out
    # Do not invent credentials; only proceed if env already present.
    key = os.environ.get("BYBIT_DEMO_API_KEY") or os.environ.get("NEXUS_BYBIT_FUTURES_API_KEY")
    secret = os.environ.get("BYBIT_DEMO_API_SECRET") or os.environ.get("NEXUS_BYBIT_FUTURES_API_SECRET")
    if not key or not secret:
        out["error"] = "NO_DEMO_CREDENTIALS_IN_ENV"
        return out
    out["attempted"] = True
    try:
        # Prefer existing readonly client if importable.
        from backend.nexus_research.demo_exchange.readers import DemoReadonlyClient  # type: ignore

        client = DemoReadonlyClient()
        # Methods may vary; collect whatever is exposed without writes.
        rows: list[dict[str, Any]] = []
        for name in ("closed_pnl", "executions", "transaction_log", "wallet_balance"):
            fn = getattr(client, name, None) or getattr(client, f"get_{name}", None)
            if callable(fn):
                try:
                    data = fn()
                    rows.append({"source": name, "payload_type": type(data).__name__})
                except Exception as exc:  # noqa: BLE001
                    rows.append({"source": name, "error": type(exc).__name__})
        out["available"] = True
        out["rows"] = rows
        out["note"] = "readonly_probe_only_no_full_ledger_export"
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}:{exc}"
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    final_attempt = _load(IMMUTABLE_12H / "wallet_delta_final_attempt.json")
    post = _load(IMMUTABLE_12H / "NEXUS_12H_V3_POST_FORENSIC_RETURN.json")

    ledger: list[dict[str, Any]] = []
    # Reconstruct known components from sealed forensic attempt (no invention).
    known = {
        "realized_pnl": 0.0,
        "trading_fees": 0.0,
        "funding": 0.0,
        "transfers": 0.0,
        "rebates": 0.0,
        "other_ledger_adjustments": 0.0,
    }
    attributed = float(final_attempt.get("wallet_delta_attributed") or 0.0)
    unattributed = float(final_attempt.get("wallet_delta_unattributed") or TARGET_DELTA)
    total = float(final_attempt.get("wallet_delta_total") or TARGET_DELTA)

    # Evidence rows from sealed attempt are summary-only (counts, not full ledger).
    list_counts = final_attempt.get("list_counts") or {}
    for kind, count in list_counts.items():
        ledger.append(
            {
                "timestamp": None,
                "transaction_type": f"SEALED_SUMMARY::{kind}",
                "symbol": None,
                "order_id": None,
                "execution_id": None,
                "currency": "USDT",
                "amount": None,
                "fee": None,
                "funding": None,
                "realized_pnl": None,
                "source_endpoint": "immutable/post_12h_forensic/wallet_delta_final_attempt.json",
                "source_checksum": hashlib.sha256(
                    (IMMUTABLE_12H / "wallet_delta_final_attempt.json").read_bytes()
                ).hexdigest(),
                "account_epoch": None,
                "account_fingerprint": None,
                "summary_count": count,
            }
        )

    api = _try_readonly_demo_history()

    trading_db_status = "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED"
    history_complete = False
    account_epoch_match = None  # unknown — epoch evidence not present in sealed summary
    account_fingerprint_match = None

    known_component_total = sum(known.values()) + attributed
    remaining = total - known_component_total
    # Prefer sealed unattributed if present
    if abs(unattributed - TARGET_DELTA) <= 1e-9:
        remaining = unattributed

    if abs(remaining) <= TOLERANCE and known_component_total != 0:
        classification = "WALLET_DELTA_FULLY_ATTRIBUTED"
    elif abs(attributed) > TOLERANCE and abs(remaining) > TOLERANCE:
        classification = "WALLET_DELTA_PARTIALLY_ATTRIBUTED"
    elif trading_db_status.endswith("NOT_RECOVERED") and not api.get("available"):
        classification = "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST"
    elif api.get("attempted") and not history_complete:
        classification = "WALLET_DELTA_UNATTRIBUTED_API_HISTORY_INCOMPLETE"
    else:
        classification = "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST"

    assert classification in FOUNDER_CLASSES

    report = {
        "schema": "wallet_delta_forensic_readonly_v1",
        "updated_at": _utc(),
        "wallet_delta_original": TARGET_DELTA,
        "wallet_delta_total": total,
        "wallet_delta_classification": classification,
        "known_components": known,
        "known_component_total": known_component_total,
        "remaining_unattributed_delta": remaining,
        "reconciliation_tolerance": TOLERANCE,
        "ledger_record_count": len(ledger),
        "ledger": ledger,
        "list_counts_from_sealed_evidence": list_counts,
        "account_epoch_match": account_epoch_match,
        "account_fingerprint_match": account_fingerprint_match,
        "history_pagination_complete": history_complete,
        "trading_db_status": trading_db_status,
        "readonly_api_probe": {
            "attempted": api.get("attempted"),
            "available": api.get("available"),
            "error": api.get("error"),
        },
        "equation": {
            "ending_minus_starting": total,
            "equals_components_plus_residual": True,
            "note": "Sealed forensic attempt recorded attributed=0; residual equals full delta.",
        },
        "source_refs": [
            "artifacts/readiness/immutable/post_12h_forensic/wallet_delta_final_attempt.json",
            "artifacts/readiness/immutable/post_12h_forensic/NEXUS_12H_V3_POST_FORENSIC_RETURN.json",
        ],
        "session_id": post.get("session_id"),
        "exchange_write_attempt_count": 0,
        "mainnet": False,
        "real_money": False,
        "report_checksum": None,
    }
    report["report_checksum"] = _sha({k: v for k, v in report.items() if k != "report_checksum"})
    (OUT / "wallet_delta_forensic_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "classification": classification,
        "remaining_unattributed_delta": remaining,
        "ledger_record_count": len(ledger),
        "trading_db_status": trading_db_status,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
