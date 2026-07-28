"""Phase 6.6 — Read-only Bybit Demo readers + exchange snapshot."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    DEFAULT_ACCOUNT_TYPE,
    DEFAULT_CATEGORY,
    STALE_MS_DEFAULT,
)
from backend.nexus_research.demo_exchange.errors import (
    MalformedResponseError,
    SchemaValidationError,
    StaleDataError,
)
from backend.nexus_research.demo_exchange.identity import DemoSnapshotIdentity
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _response_time_ms(payload: Mapping[str, Any]) -> int:
    return _as_int(payload.get("time"), 0)


def _assert_schema(payload: Mapping[str, Any]) -> None:
    if "retCode" not in payload or "result" not in payload:
        raise SchemaValidationError("missing_retCode_or_result")
    if not isinstance(payload.get("result"), (dict, list)):
        raise SchemaValidationError("result_invalid_type")


def _assert_fresh(payload: Mapping[str, Any], *, stale_ms: int, label: str) -> None:
    ts = _response_time_ms(payload)
    if ts <= 0:
        raise SchemaValidationError(f"{label}_missing_timestamp")
    age = int(time.time() * 1000) - ts
    if age > stale_ms:
        raise StaleDataError(f"stale_{label}:{age}")


@dataclass
class WalletView:
    account_type: str
    total_equity: float
    wallet_balance: float
    available_balance: float
    coin: str
    captured_at_ms: int
    raw_time_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "accountType": self.account_type,
            "totalEquity": self.total_equity,
            "walletBalance": self.wallet_balance,
            "availableBalance": self.available_balance,
            "coin": self.coin,
            "capturedAtMs": self.captured_at_ms,
            "rawTimeMs": self.raw_time_ms,
        }


@dataclass
class PositionView:
    symbol: str
    side: str
    size: float
    avg_price: float
    unrealised_pnl: float
    realised_pnl: float
    updated_at_ms: int
    position_idx: int | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    tp_trigger_by: str | None = None
    sl_trigger_by: str | None = None
    mark_price: float | None = None
    liq_price: float | None = None
    leverage: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "avgPrice": self.avg_price,
            "unrealisedPnl": self.unrealised_pnl,
            "realisedPnl": self.realised_pnl,
            "updatedAtMs": self.updated_at_ms,
            "positionIdx": self.position_idx,
            "stopLoss": self.stop_loss,
            "takeProfit": self.take_profit,
            "tpTriggerBy": self.tp_trigger_by,
            "slTriggerBy": self.sl_trigger_by,
            "markPrice": self.mark_price,
            "liqPrice": self.liq_price,
            "leverage": self.leverage,
        }


@dataclass
class OrderView:
    order_id: str
    order_link_id: str
    symbol: str
    side: str
    qty: float
    avg_price: float
    status: str
    created_at_ms: int
    updated_at_ms: int
    order_type: str | None = None
    stop_order_type: str | None = None
    trigger_price: float | None = None
    trigger_direction: str | None = None
    trigger_by: str | None = None
    leaves_qty: float | None = None
    cum_exec_qty: float | None = None
    reduce_only: bool | None = None
    close_on_trigger: bool | None = None
    position_idx: int | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    tp_trigger_by: str | None = None
    sl_trigger_by: str | None = None
    tpsl_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        normalized = normalize_order_status(self.status)
        return {
            "orderId": self.order_id,
            "orderLinkId": self.order_link_id,
            "symbol": self.symbol,
            "side": self.side,
            "orderType": self.order_type,
            "stopOrderType": self.stop_order_type,
            "triggerPrice": self.trigger_price,
            "triggerDirection": self.trigger_direction,
            "triggerBy": self.trigger_by,
            "qty": self.qty,
            "leavesQty": self.leaves_qty,
            "cumExecQty": self.cum_exec_qty,
            "avgPrice": self.avg_price,
            "reduceOnly": self.reduce_only,
            "closeOnTrigger": self.close_on_trigger,
            "positionIdx": self.position_idx,
            "orderStatus": self.status,
            "status": self.status,
            "normalizedOrderStatus": normalized,
            "createdTime": self.created_at_ms,
            "updatedTime": self.updated_at_ms,
            "createdAtMs": self.created_at_ms,
            "updatedAtMs": self.updated_at_ms,
            "takeProfit": self.take_profit,
            "stopLoss": self.stop_loss,
            "tpTriggerBy": self.tp_trigger_by,
            "slTriggerBy": self.sl_trigger_by,
            "tpslMode": self.tpsl_mode,
        }


def normalize_order_status(*candidates: Any) -> str:
    """Normalize orderStatus/status into a single verdict-friendly token."""
    raw = ""
    for c in candidates:
        if c is None:
            continue
        s = str(c).strip()
        if s:
            raw = s
            break
    if not raw:
        return "UNKNOWN"
    low = raw.lower()
    active = {"untriggered", "new", "created", "active", "partiallyfilled", "triggered"}
    terminal = {"filled", "cancelled", "canceled", "rejected", "deactivated", "expired"}
    compact = low.replace("_", "").replace(" ", "")
    if compact in active or low in {"untriggered", "new", "active"}:
        if compact == "untriggered":
            return "Untriggered"
        if compact in {"new", "created"}:
            return "New"
        if compact == "active":
            return "Active"
        if compact == "partiallyfilled":
            return "PartiallyFilled"
        if compact == "triggered":
            return "Triggered"
        return raw
    if compact in terminal:
        if compact in {"cancelled", "canceled"}:
            return "Cancelled"
        if compact == "filled":
            return "Filled"
        if compact == "rejected":
            return "Rejected"
        if compact == "deactivated":
            return "Deactivated"
        if compact == "expired":
            return "Expired"
        return raw
    return "UNKNOWN"


def _optional_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _optional_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _optional_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _optional_bool(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


@dataclass
class ExecutionView:
    exec_id: str
    order_id: str
    order_link_id: str
    symbol: str
    side: str
    qty: float
    price: float
    exec_time_ms: int
    closed_pnl: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "execId": self.exec_id,
            "orderId": self.order_id,
            "orderLinkId": self.order_link_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "price": self.price,
            "execTimeMs": self.exec_time_ms,
            "closedPnl": self.closed_pnl,
        }


class DemoWalletReader:
    def __init__(self, transport: DemoReadOnlyTransport, *, stale_ms: int = STALE_MS_DEFAULT) -> None:
        self.transport = transport
        self.stale_ms = stale_ms

    def read(self, *, account_type: str = DEFAULT_ACCOUNT_TYPE, check_stale: bool = True) -> WalletView:
        payload = self.transport.request(
            "GET",
            "/v5/account/wallet-balance",
            {"accountType": account_type},
        )
        _assert_schema(payload)
        if check_stale:
            _assert_fresh(payload, stale_ms=self.stale_ms, label="wallet")
        result = payload.get("result") or {}
        rows = result.get("list") if isinstance(result, dict) else []
        if not rows:
            raise MalformedResponseError("wallet_list_empty")
        row = rows[0]
        coins = row.get("coin") or []
        coin_row = coins[0] if coins else {}
        now = int(time.time() * 1000)
        available = _as_float(
            row.get("totalAvailableBalance")
            or row.get("availableBalance")
            or coin_row.get("availableToWithdraw")
            or coin_row.get("availableToBuy")
            or coin_row.get("availableBalance")
            or coin_row.get("equity")
        )
        wallet = _as_float(row.get("totalWalletBalance") or coin_row.get("walletBalance"))
        equity = _as_float(row.get("totalEquity") or coin_row.get("equity") or wallet)
        # Demo UTA sometimes reports available=0 while equity is free and flat.
        # Prefer equity/wallet for available when no explicit available fields exist.
        if available <= 0 and equity > 0:
            available = equity if equity > 0 else wallet
        if equity > 0:
            # Available must never exceed total equity for sizing.
            available = min(available, equity)
        return WalletView(
            account_type=str(row.get("accountType") or account_type),
            total_equity=equity,
            wallet_balance=wallet,
            available_balance=available,
            coin=str(coin_row.get("coin") or "USDT"),
            captured_at_ms=now,
            raw_time_ms=_response_time_ms(payload),
        )


class DemoPositionReader:
    def __init__(self, transport: DemoReadOnlyTransport, *, stale_ms: int = STALE_MS_DEFAULT) -> None:
        self.transport = transport
        self.stale_ms = stale_ms

    def read(
        self,
        *,
        category: str = DEFAULT_CATEGORY,
        check_stale: bool = True,
        cursor: str | None = None,
    ) -> list[PositionView]:
        params: dict[str, str] = {"category": category, "settleCoin": "USDT"}
        if cursor:
            params["cursor"] = cursor
        payload = self.transport.request("GET", "/v5/position/list", params)
        _assert_schema(payload)
        if check_stale:
            _assert_fresh(payload, stale_ms=self.stale_ms, label="position")
        result = payload.get("result") or {}
        rows = result.get("list") if isinstance(result, dict) else []
        out: list[PositionView] = []
        for row in rows or []:
            out.append(
                PositionView(
                    symbol=str(row.get("symbol") or ""),
                    side=str(row.get("side") or ""),
                    size=_as_float(row.get("size")),
                    avg_price=_as_float(row.get("avgPrice")),
                    unrealised_pnl=_as_float(row.get("unrealisedPnl")),
                    realised_pnl=_as_float(row.get("cumRealisedPnl")),
                    updated_at_ms=_as_int(row.get("updatedTime")),
                    position_idx=_optional_int(row.get("positionIdx")),
                    stop_loss=_optional_float(row.get("stopLoss")),
                    take_profit=_optional_float(row.get("takeProfit")),
                    tp_trigger_by=_optional_str(row.get("tpTriggerBy")),
                    sl_trigger_by=_optional_str(row.get("slTriggerBy")),
                    mark_price=_optional_float(row.get("markPrice")),
                    liq_price=_optional_float(row.get("liqPrice") or row.get("liquidationPrice")),
                    leverage=_optional_float(row.get("leverage")),
                )
            )
        return out


class DemoOpenOrderReader:
    def __init__(self, transport: DemoReadOnlyTransport) -> None:
        self.transport = transport

    def read(
        self,
        *,
        category: str = DEFAULT_CATEGORY,
        max_pages: int = 5,
    ) -> list[OrderView]:
        out: list[OrderView] = []
        cursor = ""
        for page in range(1, max_pages + 1):
            params: dict[str, str] = {"category": category, "settleCoin": "USDT"}
            if cursor:
                params["cursor"] = cursor
            payload = self.transport.request(
                "GET",
                "/v5/order/realtime",
                params,
                fixture_kwargs={"page": page},
            )
            _assert_schema(payload)
            result = payload.get("result") or {}
            rows = result.get("list") if isinstance(result, dict) else []
            for row in rows or []:
                out.append(_parse_order(row))
            cursor = str((result or {}).get("nextPageCursor") or "")
            if not cursor:
                break
        return out


class DemoOrderHistoryReader:
    def __init__(self, transport: DemoReadOnlyTransport) -> None:
        self.transport = transport

    def read(self, *, category: str = DEFAULT_CATEGORY) -> list[OrderView]:
        payload = self.transport.request(
            "GET",
            "/v5/order/history",
            {"category": category, "settleCoin": "USDT"},
        )
        _assert_schema(payload)
        result = payload.get("result") or {}
        rows = result.get("list") if isinstance(result, dict) else []
        return [_parse_order(row) for row in (rows or [])]


class DemoExecutionReader:
    def __init__(self, transport: DemoReadOnlyTransport) -> None:
        self.transport = transport

    def read(self, *, category: str = DEFAULT_CATEGORY) -> list[ExecutionView]:
        payload = self.transport.request(
            "GET",
            "/v5/execution/list",
            {"category": category},
        )
        _assert_schema(payload)
        result = payload.get("result") or {}
        rows = result.get("list") if isinstance(result, dict) else []
        out: list[ExecutionView] = []
        for row in rows or []:
            out.append(
                ExecutionView(
                    exec_id=str(row.get("execId") or ""),
                    order_id=str(row.get("orderId") or ""),
                    order_link_id=str(row.get("orderLinkId") or ""),
                    symbol=str(row.get("symbol") or ""),
                    side=str(row.get("side") or ""),
                    qty=_as_float(row.get("execQty")),
                    price=_as_float(row.get("execPrice")),
                    exec_time_ms=_as_int(row.get("execTime")),
                    closed_pnl=_as_float(row.get("closedPnl")),
                )
            )
        return out


def _parse_order(row: Mapping[str, Any]) -> OrderView:
    status_raw = row.get("orderStatus")
    if status_raw is None or str(status_raw).strip() == "":
        status_raw = row.get("status")
    status = str(status_raw or "")
    return OrderView(
        order_id=str(row.get("orderId") or ""),
        order_link_id=str(row.get("orderLinkId") or ""),
        symbol=str(row.get("symbol") or ""),
        side=str(row.get("side") or ""),
        qty=_as_float(row.get("qty")),
        avg_price=_as_float(row.get("avgPrice")),
        status=status,
        created_at_ms=_as_int(row.get("createdTime") or row.get("createdAtMs")),
        updated_at_ms=_as_int(row.get("updatedTime") or row.get("updatedAtMs")),
        order_type=_optional_str(row.get("orderType")),
        stop_order_type=_optional_str(row.get("stopOrderType")),
        trigger_price=_optional_float(row.get("triggerPrice")),
        trigger_direction=_optional_str(row.get("triggerDirection")),
        trigger_by=_optional_str(row.get("triggerBy")),
        leaves_qty=_optional_float(row.get("leavesQty")),
        cum_exec_qty=_optional_float(row.get("cumExecQty")),
        reduce_only=_optional_bool(row.get("reduceOnly")),
        close_on_trigger=_optional_bool(row.get("closeOnTrigger")),
        position_idx=_optional_int(row.get("positionIdx")),
        take_profit=_optional_float(row.get("takeProfit")),
        stop_loss=_optional_float(row.get("stopLoss")),
        tp_trigger_by=_optional_str(row.get("tpTriggerBy")),
        sl_trigger_by=_optional_str(row.get("slTriggerBy")),
        tpsl_mode=_optional_str(row.get("tpslMode")),
    )


@dataclass
class DemoExchangeSnapshot:
    identity: DemoSnapshotIdentity
    wallet: WalletView | None = None
    positions: list[PositionView] = field(default_factory=list)
    open_orders: list[OrderView] = field(default_factory=list)
    order_history: list[OrderView] = field(default_factory=list)
    executions: list[ExecutionView] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def capture(
        cls,
        transport: DemoReadOnlyTransport,
        *,
        account_id: str = ACCOUNT_BYBIT_DEMO,
        check_stale: bool = True,
    ) -> "DemoExchangeSnapshot":
        identity = DemoSnapshotIdentity(account_id=account_id)
        snap = cls(identity=identity)
        try:
            snap.wallet = DemoWalletReader(transport).read(check_stale=check_stale)
        except Exception as exc:  # noqa: BLE001
            snap.errors.append(f"wallet:{type(exc).__name__}")
        try:
            snap.positions = DemoPositionReader(transport).read(check_stale=check_stale)
        except Exception as exc:  # noqa: BLE001
            snap.errors.append(f"positions:{type(exc).__name__}")
        try:
            snap.open_orders = DemoOpenOrderReader(transport).read()
        except Exception as exc:  # noqa: BLE001
            snap.errors.append(f"open_orders:{type(exc).__name__}")
        try:
            snap.order_history = DemoOrderHistoryReader(transport).read()
        except Exception as exc:  # noqa: BLE001
            snap.errors.append(f"order_history:{type(exc).__name__}")
        try:
            snap.executions = DemoExecutionReader(transport).read()
        except Exception as exc:  # noqa: BLE001
            snap.errors.append(f"executions:{type(exc).__name__}")
        return snap

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "wallet": self.wallet.to_dict() if self.wallet else None,
            "positions": [p.to_dict() for p in self.positions],
            "openOrders": [o.to_dict() for o in self.open_orders],
            "orderHistory": [o.to_dict() for o in self.order_history],
            "executions": [e.to_dict() for e in self.executions],
            "errors": list(self.errors),
            "accountId": self.identity.account_id,
        }
