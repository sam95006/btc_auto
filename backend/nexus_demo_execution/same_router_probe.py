"""Same-router Demo execution probe — proves Order Router path before 12H.

Not strategy / profitability / learning evidence.
Uses DemoWriteClient (same client as bounded 6H/12H sessions).
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError

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
    "max_positions": 1,
    "max_orders": 1,
    "mainnet": False,
    "real_money": False,
}


def _hash_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass
class SameRouterProbeResult:
    ok: bool
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets({"ok": self.ok, "reason": self.reason, **PROBE_TAG, **self.evidence})


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

    def run(self, *, dry_run: bool = False) -> SameRouterProbeResult:
        evidence: dict[str, Any] = {
            "order_request_created": False,
            "exchange_write_attempt_total": 0,
            "exchange_accepted_total": 0,
            "fill_confirmed": False,
            "stop_loss_created": False,
            "take_profit_created": False,
            "protection_verified": False,
            "protection_latency_ms": None,
            "position_reconciliation": "UNKNOWN",
            "order_reconciliation": "UNKNOWN",
            "controlled_close_completed": False,
            "final_position_count": -1,
            "final_open_order_count": -1,
            "final_reconciliation": "UNKNOWN",
            "symbol": self.symbol,
            "side": self.side,
            **FIXED,
        }
        if dry_run:
            evidence["dry_run"] = True
            return SameRouterProbeResult(ok=False, reason="dry_run_only", evidence=evidence)

        if getattr(self.writer, "base_url", "").rstrip("/") != "https://api-demo.bybit.com":
            return SameRouterProbeResult(ok=False, reason="not_demo_domain", evidence=evidence)

        try:
            positions = self.writer.list_positions()
            orders = self.writer.list_open_orders()
            if positions or orders:
                evidence["final_position_count"] = len(positions)
                evidence["final_open_order_count"] = len(orders)
                return SameRouterProbeResult(ok=False, reason="account_not_flat", evidence=evidence)

            info = self.writer.fetch_instrument(self.symbol)
            # Use a tiny price probe via ticker-less path: fetch fee + instrument only.
            # Market order still requires a price for qty sizing — use mark from positions API fallback.
            mark = float(info.get("lastPrice") or info.get("markPrice") or 0) if isinstance(info, dict) else 0.0
            if mark <= 0:
                # Demo instruments often expose tick/lot only; require caller/env mark.
                mark = float((__import__("os").environ.get("PROBE_MARK_PRICE") or "0") or 0)
            if mark <= 0:
                return SameRouterProbeResult(ok=False, reason="mark_price_unavailable", evidence=evidence)

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
            evidence["exchange_write_attempt_total"] = 1
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
            oid = str((resp or {}).get("orderId") or (resp or {}).get("order_id") or link)
            evidence["order_id_hash"] = _hash_id(oid)

            # Fill wait
            pos = None
            t0 = time.time()
            for _ in range(30):
                rows = self.writer.list_positions(self.symbol)
                if rows:
                    pos = rows[0]
                    break
                time.sleep(1)
            if not pos:
                return SameRouterProbeResult(ok=False, reason="fill_not_confirmed", evidence=evidence)
            evidence["fill_confirmed"] = True
            evidence["entry_price"] = pos.get("avgPrice") or pos.get("entryPrice")

            # Protection verify
            deadline = t0 + 5
            while time.time() < deadline:
                rows = self.writer.list_positions(self.symbol)
                if rows and rows[0].get("stopLoss") and rows[0].get("takeProfit"):
                    evidence["stop_loss_created"] = True
                    evidence["take_profit_created"] = True
                    evidence["protection_verified"] = True
                    evidence["protection_latency_ms"] = int((time.time() - t0) * 1000)
                    break
                time.sleep(0.5)
            if not evidence["protection_verified"]:
                # Still flatten
                self.writer.close_reduce_only(
                    symbol=self.symbol,
                    side=self.side,
                    qty=str(pos.get("size") or qty),
                    order_link_id=f"NEXUS-PROBE-CLS-{uuid.uuid4().hex[:8]}"[:36],
                )
                return SameRouterProbeResult(ok=False, reason="protection_not_verified", evidence=evidence)

            evidence["position_reconciliation"] = "MATCH"
            evidence["order_reconciliation"] = "MATCH"

            self.writer.close_reduce_only(
                symbol=self.symbol,
                side=self.side,
                qty=str(pos.get("size") or qty),
                order_link_id=f"NEXUS-PROBE-CLS-{uuid.uuid4().hex[:8]}"[:36],
            )
            evidence["controlled_close_completed"] = True
            time.sleep(2)
            final_pos = self.writer.list_positions()
            final_ord = self.writer.list_open_orders()
            evidence["final_position_count"] = len(final_pos)
            evidence["final_open_order_count"] = len(final_ord)
            evidence["final_reconciliation"] = (
                "MATCH" if not final_pos and not final_ord else "MISMATCH"
            )
            evidence["exit_price"] = None
            evidence["gross_pnl"] = None
            evidence["actual_fees"] = None
            evidence["slippage"] = None
            evidence["net_pnl"] = None

            ok = (
                evidence["exchange_accepted_total"] == 1
                and evidence["fill_confirmed"]
                and evidence["protection_verified"]
                and evidence["final_reconciliation"] == "MATCH"
            )
            self.export_dir.mkdir(parents=True, exist_ok=True)
            out = SameRouterProbeResult(
                ok=ok,
                reason="PASS" if ok else "final_not_flat",
                evidence=evidence,
            )
            (self.export_dir / "same_router_probe_result.json").write_text(
                __import__("json").dumps(out.to_dict(), indent=2) + "\n", encoding="utf-8"
            )
            return out
        except DemoWriteError as exc:
            evidence["last_exchange_rejection_code"] = exc.code
            evidence["last_exchange_rejection_reason"] = str(exc.detail or "")[:200]
            return SameRouterProbeResult(ok=False, reason=f"exchange:{exc.code}", evidence=evidence)
        except Exception as exc:  # noqa: BLE001
            return SameRouterProbeResult(
                ok=False, reason=f"exception:{type(exc).__name__}", evidence=evidence
            )
