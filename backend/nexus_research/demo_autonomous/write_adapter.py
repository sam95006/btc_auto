"""Demo write adapter — session-gated place/cancel/close/leverage."""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_autonomous.session_authorization import (
    AuthorizationValidator,
    get_authorization_validator,
)
from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
from backend.nexus_research.demo_execution.intent import DemoOrderIntent
from backend.nexus_research.demo_execution.state_machine import DemoOrderState, DemoOrderStateMachine


@dataclass
class WriteResult:
    ok: bool
    path: str
    ret_code: int = -1
    ret_msg: str = ""
    order_id: str | None = None
    dry_run: bool = False
    raw_safe: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "retCode": self.ret_code,
            "retMsg": self.ret_msg,
            "orderId": self.order_id,
            "dryRun": self.dry_run,
            "error": self.error,
            "secretSafe": True,
        }


def make_order_link_id(symbol: str, side: str, qty: float, leverage: int) -> str:
    raw = f"nx-auto:{symbol}:{side}:{qty}:{leverage}:{int(time.time())}"
    return f"nxa-{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


class AutonomousDemoOrderAdapter:
    """Writes only when session authorization is active."""

    def __init__(
        self,
        transport: DemoWriteTransport,
        *,
        auth: AuthorizationValidator | None = None,
    ) -> None:
        self.transport = transport
        self.auth = auth or get_authorization_validator()

    def set_leverage(self, symbol: str, leverage: int) -> WriteResult:
        body = {
            "category": "linear",
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage),
        }
        return self._post("/v5/position/set-leverage", body)

    def ensure_isolated(self, symbol: str, leverage: int) -> WriteResult:
        body = {
            "category": "linear",
            "symbol": symbol,
            "tradeMode": 1,  # isolated
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage),
        }
        return self._post("/v5/position/switch-isolated", body)

    def place_order(self, intent: DemoOrderIntent, *, reduce_only: bool = False) -> WriteResult:
        blocks = self.auth.validate_order_bounds(
            symbol=intent.symbol,
            side=intent.side,
            risk_pct=0.0,  # risk checked upstream
            open_positions=0,
            pending_orders=0,
        )
        # risk checked by orchestrator; here only side/symbol
        blocks = [b for b in blocks if not b.startswith("risk_pct")]
        if blocks:
            return WriteResult(False, "/v5/order/create", error=";".join(blocks))

        body: dict[str, Any] = {
            "category": "linear",
            "symbol": intent.symbol,
            "side": intent.side,
            "orderType": "Market",
            "qty": str(intent.qty),
            "timeInForce": "IOC",
            "orderLinkId": intent.client_order_id,
            "reduceOnly": reduce_only,
            "positionIdx": 0,
        }
        if intent.stop_loss_price:
            body["stopLoss"] = str(intent.stop_loss_price)
            body["slTriggerBy"] = "MarkPrice"
        if intent.take_profit_price:
            body["takeProfit"] = str(intent.take_profit_price)
            body["tpTriggerBy"] = "MarkPrice"
        return self._post("/v5/order/create", body)

    def set_trading_stop(
        self,
        symbol: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> WriteResult:
        body: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "positionIdx": 0,
        }
        if stop_loss is not None:
            body["stopLoss"] = str(stop_loss)
            body["slTriggerBy"] = "MarkPrice"
        if take_profit is not None:
            body["takeProfit"] = str(take_profit)
            body["tpTriggerBy"] = "MarkPrice"
        return self._post("/v5/position/trading-stop", body)

    def cancel_order(self, symbol: str, *, order_id: str | None = None, order_link_id: str | None = None) -> WriteResult:
        body: dict[str, Any] = {"category": "linear", "symbol": symbol}
        if order_id:
            body["orderId"] = order_id
        if order_link_id:
            body["orderLinkId"] = order_link_id
        return self._post("/v5/order/cancel", body)

    def close_position(self, symbol: str, side: str, qty: float) -> WriteResult:
        # Closing long => Sell reduceOnly; closing short => Buy reduceOnly
        close_side = "Sell" if side in ("Buy", "LONG", "Long") else "Buy"
        intent = DemoOrderIntent(
            intent_id=f"close-{uuid.uuid4().hex[:12]}",
            symbol=symbol,
            side=close_side,
            qty=qty,
            leverage=1,
            entry_price=0.0,
            stop_loss_price=0.0,
            take_profit_price=None,
            risk_tier="VALIDATION",
            client_order_id=make_order_link_id(symbol, close_side, qty, 1),
            source="autonomous_close",
        )
        return self.place_order(intent, reduce_only=True)

    def _post(self, path: str, body: dict[str, Any]) -> WriteResult:
        try:
            resp = self.transport.post(path, body)
        except Exception as exc:  # noqa: BLE001 — map to WriteResult
            return WriteResult(False, path, error=f"{type(exc).__name__}")
        ret = int(resp.get("retCode", -1))
        result = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        order_id = None
        if isinstance(result, dict):
            order_id = result.get("orderId") or result.get("orderLinkId")
        safe = {
            "retCode": ret,
            "retMsg": str(resp.get("retMsg") or "")[:120],
            "hasResult": bool(result),
            "dryRun": bool(result.get("dryRun")) if isinstance(result, dict) else False,
        }
        return WriteResult(
            ok=ret == 0,
            path=path,
            ret_code=ret,
            ret_msg=str(resp.get("retMsg") or ""),
            order_id=str(order_id) if order_id else None,
            dry_run=bool(safe["dryRun"]),
            raw_safe=safe,
        )
