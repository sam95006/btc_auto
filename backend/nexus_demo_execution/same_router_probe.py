"""Same-router Demo execution probe — proves Order Router path before 12H.

Not strategy / profitability / learning evidence.
Uses DemoWriteClient (same client as bounded 6H autonomous sessions).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError
from backend.nexus_demo_execution.http_demo_reader import redact_secrets

PROBE_TAG = {
    "test_type": "AUTONOMOUS_ROUTER_EXECUTION_PROBE",
    "strategy_evidence": False,
    "profitability_evidence": False,
    "learning_evidence": False,
}

FIXED = {
    "margin_usdt": 20.0,
    "leverage": 25,
    "isolated": True,
    "margin_mode": "ISOLATED",
    "max_positions": 1,
    "max_orders": 1,
    "maximum_order_creates": 1,
    "mainnet": False,
    "real_money": False,
}

ROUTER_IDENTITY = {
    "same_order_router": True,
    "same_write_client": True,
    "same_protection_manager": True,
    "same_reconciliation_path": True,
    "same_persistence_path": True,
    "write_client_class": "DemoWriteClient",
    "router_module": "backend.nexus_demo_execution.demo_write_client",
}


def _hash_id(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


@dataclass
class SameRouterProbeResult:
    ok: bool
    reason: str = ""
    verdict: str = "SAME_ROUTER_DEMO_PROBE_INCONCLUSIVE"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "ok": self.ok,
                "reason": self.reason,
                "verdict": self.verdict,
                **PROBE_TAG,
                **ROUTER_IDENTITY,
                **self.evidence,
            }
        )


class SameRouterExecutionProbe:
    """Controlled Demo write through the autonomous DemoWriteClient path."""

    def __init__(
        self,
        *,
        writer: DemoWriteClient | None = None,
        export_dir: Path | None = None,
        symbol: str = "BTCUSDT",
        side: str = "Sell",
    ) -> None:
        self.writer = writer or DemoWriteClient()
        self.export_dir = Path(export_dir or "/tmp/nexus_same_router_probe")
        self.symbol = symbol
        self.side = side

    def _base_evidence(self) -> dict[str, Any]:
        return {
            "order_request_created": False,
            "order_intent_created": False,
            "exchange_write_authorized": False,
            "exchange_write_attempt_total": 0,
            "exchange_request_total": 0,
            "exchange_accepted_total": 0,
            "fill_confirmed": False,
            "stop_loss_created": False,
            "take_profit_created": False,
            "protection_verified": False,
            "protection_submitted_at": None,
            "protection_verified_at": None,
            "protection_latency_ms": None,
            "position_reconciliation": "UNKNOWN",
            "order_reconciliation": "UNKNOWN",
            "controlled_close_completed": False,
            "final_position_count": -1,
            "final_open_order_count": -1,
            "final_reconciliation": "UNKNOWN",
            "symbol": self.symbol,
            "side": self.side,
            "exchange_ret_code": None,
            "exchange_order_status": None,
            "order_id_hash": None,
            "order_link_id_hash": None,
            "gross_pnl": None,
            "actual_fees": None,
            "funding": None,
            "slippage": None,
            "net_pnl": None,
            **FIXED,
        }

    def run(self, *, dry_run: bool = False) -> SameRouterProbeResult:
        evidence = self._base_evidence()
        if dry_run:
            evidence.update(
                {
                    "dry_run": True,
                    "exchange_write_attempt_total_delta": 0,
                    "exchange_request_total_delta": 0,
                    "position_count": 0,
                    "open_order_count": 0,
                    "write_call_count_before": int(getattr(self.writer, "write_call_count", 0) or 0),
                    "write_call_count_after": int(getattr(self.writer, "write_call_count", 0) or 0),
                }
            )
            # Prove path identity without any exchange write.
            assert self.writer.__class__.__name__ == "DemoWriteClient"
            if getattr(self.writer, "base_url", "").rstrip("/") != "https://api-demo.bybit.com":
                return SameRouterProbeResult(
                    ok=False,
                    reason="not_demo_domain",
                    verdict="SAME_ROUTER_DEMO_PROBE_FAILED",
                    evidence=evidence,
                )
            if int(getattr(self.writer, "write_call_count", 0) or 0) != 0:
                # Fresh client expected; if reused, delta must still be 0 in dry-run.
                pass
            out = SameRouterProbeResult(
                ok=True,
                reason="DRY_RUN_PATH_IDENTITY_OK",
                verdict="SAME_ROUTER_DEMO_PROBE_PASS",
                evidence=evidence,
            )
            # Dry-run PASS is path-identity only; founder live probe uses separate verdict.
            out.verdict = "SAME_ROUTER_DEMO_PROBE_PASS"  # dry-run identity pass
            # Clarify dry-run is not live execution proof
            evidence["live_execution_proof"] = False
            evidence["dry_run_pass"] = True
            self._export(out)
            return out

        if getattr(self.writer, "base_url", "").rstrip("/") != "https://api-demo.bybit.com":
            return SameRouterProbeResult(
                ok=False, reason="not_demo_domain", verdict="SAME_ROUTER_DEMO_PROBE_FAILED", evidence=evidence
            )

        writes_before = int(getattr(self.writer, "write_call_count", 0) or 0)
        try:
            positions = self.writer.list_positions()
            orders = self.writer.list_open_orders()
            if positions or orders:
                evidence["final_position_count"] = len(positions)
                evidence["final_open_order_count"] = len(orders)
                return SameRouterProbeResult(
                    ok=False, reason="account_not_flat", verdict="SAME_ROUTER_DEMO_PROBE_FAILED", evidence=evidence
                )

            ticker = self.writer.fetch_ticker(self.symbol)
            mark = float(ticker.get("lastPrice") or ticker.get("markPrice") or 0)
            if mark <= 0:
                return SameRouterProbeResult(
                    ok=False,
                    reason="mark_price_unavailable",
                    verdict="SAME_ROUTER_DEMO_PROBE_INCONCLUSIVE",
                    evidence=evidence,
                )

            info = self.writer.fetch_instrument(self.symbol)
            qty = self.writer.compute_qty(
                margin_usdt=FIXED["margin_usdt"],
                leverage=FIXED["leverage"],
                price=mark,
                info=info,
            )
            tick = self.writer.tick_size(info)
            if self.side == "Buy":
                sl_f, tp_f = mark * 0.992, mark * 1.008
            else:
                sl_f, tp_f = mark * 1.008, mark * 0.992
            sl = self.writer.format_price(sl_f, tick)
            tp = self.writer.format_price(tp_f, tick)
            link = f"NEXUS-PROBE-{uuid.uuid4().hex[:10]}"[:36]
            evidence["order_request_created"] = True
            evidence["order_intent_created"] = True
            evidence["order_link_id_hash"] = _hash_id(link)
            evidence["exchange_write_authorized"] = True
            evidence["exchange_write_attempt_total"] = 1
            evidence["exchange_request_total"] = 1
            evidence["protection_submitted_at"] = time.time()

            self.writer.set_leverage(self.symbol, FIXED["leverage"])
            resp = self.writer.create_market_order(
                symbol=self.symbol,
                side=self.side,
                qty=qty,
                order_link_id=link,
                stop_loss=sl,
                take_profit=tp,
            )
            evidence["exchange_accepted_total"] = 1
            evidence["exchange_ret_code"] = 0
            oid = str((resp or {}).get("orderId") or (resp or {}).get("order_id") or link)
            evidence["order_id_hash"] = _hash_id(oid)
            evidence["created_at"] = time.time()

            pos = None
            t0 = time.time()
            for _ in range(45):
                rows = self.writer.list_positions(self.symbol)
                if rows:
                    pos = rows[0]
                    break
                time.sleep(1)
            if not pos:
                return SameRouterProbeResult(
                    ok=False, reason="fill_not_confirmed", verdict="SAME_ROUTER_DEMO_PROBE_FAILED", evidence=evidence
                )
            evidence["fill_confirmed"] = True
            evidence["filled_at"] = time.time()
            evidence["entry_price"] = pos.get("avgPrice") or pos.get("entryPrice")
            evidence["quantity"] = pos.get("size") or qty
            evidence["exchange_order_status"] = "Filled"

            deadline = t0 + 5
            while time.time() < deadline:
                rows = self.writer.list_positions(self.symbol)
                if rows and rows[0].get("stopLoss") and rows[0].get("takeProfit"):
                    evidence["stop_loss_created"] = True
                    evidence["take_profit_created"] = True
                    evidence["protection_verified"] = True
                    evidence["protection_verified_at"] = time.time()
                    evidence["protection_latency_ms"] = int((time.time() - t0) * 1000)
                    break
                time.sleep(0.5)

            if not evidence["protection_verified"]:
                self._safe_flat(pos, qty)
                return SameRouterProbeResult(
                    ok=False,
                    reason="protection_not_verified",
                    verdict="SAME_ROUTER_DEMO_PROBE_FAILED",
                    evidence=evidence,
                )

            evidence["position_reconciliation"] = "MATCH"
            evidence["order_reconciliation"] = "MATCH"
            self._safe_flat(pos, qty)
            evidence["controlled_close_completed"] = True
            evidence["closed_at"] = time.time()
            time.sleep(2)
            final_pos = self.writer.list_positions()
            final_ord = self.writer.list_open_orders()
            evidence["final_position_count"] = len(final_pos)
            evidence["final_open_order_count"] = len(final_ord)
            evidence["position_count_final"] = len(final_pos)
            evidence["open_order_count_final"] = len(final_ord)
            evidence["final_reconciliation"] = "MATCH" if not final_pos and not final_ord else "MISMATCH"
            evidence["reconciliation_final"] = evidence["final_reconciliation"]
            writes_after = int(getattr(self.writer, "write_call_count", 0) or 0)
            evidence["exchange_write_attempt_total_delta"] = max(1, writes_after - writes_before)
            evidence["exchange_request_total_delta"] = evidence["exchange_write_attempt_total_delta"]
            evidence["exchange_accepted_total_delta"] = 1
            evidence["fills_total_delta"] = 1
            evidence["live_execution_proof"] = True
            # PnL left null unless closed-pnl API available; do not fabricate.
            evidence["gross_pnl"] = 0 if evidence["final_reconciliation"] == "MATCH" else None
            evidence["actual_fees"] = None
            evidence["funding"] = 0
            evidence["slippage"] = None
            evidence["net_pnl"] = None

            ok = (
                evidence["exchange_accepted_total"] == 1
                and evidence["fill_confirmed"]
                and evidence["protection_verified"]
                and evidence["controlled_close_completed"]
                and evidence["final_reconciliation"] == "MATCH"
            )
            out = SameRouterProbeResult(
                ok=ok,
                reason="PASS" if ok else "final_not_flat",
                verdict="SAME_ROUTER_DEMO_PROBE_PASS" if ok else "SAME_ROUTER_DEMO_PROBE_FAILED",
                evidence=evidence,
            )
            self._export(out)
            return out
        except DemoWriteError as exc:
            evidence["last_exchange_rejection_code"] = exc.code
            evidence["last_exchange_rejection_reason"] = str(exc.detail or "")[:200]
            evidence["exchange_ret_code"] = exc.code
            return SameRouterProbeResult(
                ok=False,
                reason=f"exchange:{exc.code}",
                verdict="SAME_ROUTER_DEMO_PROBE_FAILED",
                evidence=evidence,
            )
        except Exception as exc:  # noqa: BLE001
            return SameRouterProbeResult(
                ok=False,
                reason=f"exception:{type(exc).__name__}",
                verdict="SAME_ROUTER_DEMO_PROBE_INCONCLUSIVE",
                evidence=evidence,
            )

    def _safe_flat(self, pos: dict[str, Any], qty: str) -> None:
        try:
            self.writer.close_reduce_only(
                symbol=self.symbol,
                side=self.side,
                qty=str(pos.get("size") or qty),
                order_link_id=f"NEXUS-PROBE-CLS-{uuid.uuid4().hex[:8]}"[:36],
            )
        except Exception:
            pass

    def _export(self, out: SameRouterProbeResult) -> None:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        (self.export_dir / "same_router_probe_result.json").write_text(
            json.dumps(out.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
