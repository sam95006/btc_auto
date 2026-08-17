"""Read-only recovery for an outcome-unknown Bybit Demo P1 run."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_persistence_pg.pool import PostgresPool

CAMPAIGN_ID = "bybit-demo-p1-qualification"
UNRESOLVED_STATES = ("SUBMITTING", "SUBMIT_UNKNOWN", "ACCEPTED", "NEW", "PARTIALLY_FILLED", "FILLED", "CLOSE_PENDING", "RECONCILIATION_REQUIRED")


def _database_url() -> str:
    return (os.environ.get("NEXUS_POSTGRES_URL") or os.environ.get("DATABASE_URL") or "").strip()


def _write_evidence(payload: dict[str, Any]) -> None:
    destination = Path(os.environ.get("P1_EVIDENCE_PATH") or "/tmp/nexus_demo_validation/p1_recovery_evidence.json")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError:
        return


def _ledger_summary(pool: PostgresPool) -> dict[str, Any]:
    versions = {str(row[0]) for row in pool.fetchall("SELECT version FROM nexus.schema_migrations")}
    rows = pool.fetchall(
        """
        SELECT state, reduce_only, COUNT(*)
        FROM nexus.bybit_demo_order_intents
        WHERE campaign_id=%s
        GROUP BY state, reduce_only
        """,
        (CAMPAIGN_ID,),
    )
    state_counts = {f"{row[0]}:{'close' if row[1] else 'entry'}": int(row[2]) for row in rows}
    unresolved = sum(
        count for key, count in state_counts.items() if key.split(":", 1)[0] in UNRESOLVED_STATES
    )
    history_count = int(
        pool.fetchval(
            """
            SELECT COUNT(*)
            FROM nexus.bybit_demo_order_state_history h
            JOIN nexus.bybit_demo_order_intents i ON i.order_intent_id=h.order_intent_id
            WHERE i.campaign_id=%s
            """,
            (CAMPAIGN_ID,),
        )
        or 0
    )
    return {
        "migration_0005_present": "0005" in versions,
        "migration_0006_present": "0006" in versions,
        "p1_intent_count": sum(state_counts.values()),
        "p1_unresolved_ledger_count": unresolved,
        "p1_state_counts": state_counts,
        "p1_transition_history_count": history_count,
    }


def run_recovery() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "P1_RUN2_RECOVERY_CLEAR": "HOLD",
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
        "read_only_recovery": True,
        "campaign": CAMPAIGN_ID,
        "exchange_write_call_count": 0,
        "create_order_calls": 0,
        "error": None,
    }
    pool: PostgresPool | None = None
    try:
        client = DemoWriteClient()
        open_orders = list(client.list_open_orders() or [])
        positions = list(client.list_positions() or [])
        executions = list(client.list_executions(limit=100) or [])
        closed_pnl = list(client.list_closed_pnl(limit=100) or [])
        order_history = list(
            ((client._get("/v5/order/history", {"category": "linear", "limit": "100"}).get("result") or {}).get("list") or [])
        )
        p1_exchange_rows = [
            row
            for row in order_history + executions + closed_pnl
            if str(row.get("orderLinkId") or "").startswith("nx-")
        ]
        evidence.update(
            {
                "run2_order_count_found": len(open_orders),
                "run2_position_count_found": len(positions),
                "recent_order_history_count": len(order_history),
                "recent_execution_count": len(executions),
                "recent_closed_pnl_count": len(closed_pnl),
                "p1_identity_exchange_row_count": len(p1_exchange_rows),
            }
        )
        url = _database_url()
        if not url:
            evidence["error"] = "ledger_dsn_missing"
            return evidence
        pool = PostgresPool(url)
        pool.open()
        ledger = _ledger_summary(pool)
        evidence.update(ledger)
        clear = (
            not open_orders
            and not positions
            and ledger["p1_unresolved_ledger_count"] == 0
            and ledger["migration_0005_present"]
            and ledger["migration_0006_present"]
        )
        evidence["P1_RUN2_RECOVERY_CLEAR"] = "PASS" if clear else "HOLD"
        if not clear:
            evidence["error"] = "recovery_not_clear"
        return evidence
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = f"{type(exc).__name__}"
        return evidence
    finally:
        if pool is not None:
            pool.close()


def main() -> int:
    evidence = redact_secrets(run_recovery())
    _write_evidence(evidence)
    print(json.dumps(evidence, default=str))
    return 0 if evidence.get("P1_RUN2_RECOVERY_CLEAR") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
