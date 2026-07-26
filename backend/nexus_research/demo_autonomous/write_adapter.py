"""Demo write adapter — UTA/Demo-compatible stepwise writes with stage traces."""
from __future__ import annotations

import hashlib
import math
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable

from backend.nexus_research.demo_autonomous.account_mode import (
    DemoAccountModeResolver,
    DemoAccountModeTruth,
    DemoInstrumentTruth,
    DemoMarginModeCompatibility,
    DemoPositionIndexResolver,
    DemoPositionModeResolver,
    DemoSymbolPositionTruth,
)
from backend.nexus_research.demo_autonomous.session_authorization import (
    AuthorizationValidator,
    get_authorization_validator,
)
from backend.nexus_research.demo_autonomous.write_trace import (
    DEMO_SUPPORTED_WRITE_PATHS,
    DEMO_UNSUPPORTED_WRITE_PATHS,
    BybitDemoErrorClassifier,
    DemoWriteRequestMetadata,
    DemoWriteStageTrace,
    WriteFailureClass,
    WriteStage,
    hash_order_link_id,
)
from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
from backend.nexus_research.demo_execution.intent import DemoOrderIntent


GetJson = Callable[[str, dict[str, Any] | None], dict[str, Any]]


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
    already_satisfied: bool = False
    stage: str | None = None
    classification: str | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "retCode": self.ret_code,
            "retMsg": self.ret_msg,
            "orderId": self.order_id,
            "dryRun": self.dry_run,
            "error": self.error,
            "alreadySatisfied": self.already_satisfied,
            "stage": self.stage,
            "classification": self.classification,
            "meta": self.meta,
            "secretSafe": True,
        }


def make_order_link_id(symbol: str, side: str, qty: float, leverage: int) -> str:
    raw = f"nx-auto:{symbol}:{side}:{qty}:{leverage}:{int(time.time())}"
    return f"nxa-{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def round_qty_to_step(qty: float, qty_step: float, min_qty: float = 0.0) -> float:
    if qty_step <= 0:
        return qty
    step = Decimal(str(qty_step))
    q = Decimal(str(qty))
    rounded = (q / step).to_integral_value(rounding=ROUND_DOWN) * step
    out = float(rounded)
    if min_qty > 0 and out < min_qty:
        return 0.0
    return out


class AutonomousDemoOrderAdapter:
    """Session-gated Demo writes. Never uses switch-isolated (not on Demo allowlist)."""

    def __init__(
        self,
        transport: DemoWriteTransport,
        *,
        auth: AuthorizationValidator | None = None,
        get_json: GetJson | None = None,
    ) -> None:
        self.transport = transport
        self.auth = auth or get_authorization_validator()
        self.get_json = get_json
        self.classifier = BybitDemoErrorClassifier()
        self.account_resolver = DemoAccountModeResolver()
        self.position_resolver = DemoPositionModeResolver()
        self.idx_resolver = DemoPositionIndexResolver()
        self.margin_compat = DemoMarginModeCompatibility()
        self.last_trace = DemoWriteStageTrace()
        self.last_account: DemoAccountModeTruth | None = None

    def refresh_account_truth(self) -> DemoAccountModeTruth:
        if self.get_json is None:
            truth = DemoAccountModeTruth(notes=["get_json_unavailable_assume_UNIFIED"])
            self.last_account = truth
            return truth
        truth = self.account_resolver.resolve(self.get_json)
        self.last_account = truth
        return truth

    def set_leverage(self, symbol: str, leverage: int, *, category: str = "linear") -> WriteResult:
        stage = WriteStage.STEP_1_SET_LEVERAGE
        path = "/v5/position/set-leverage"
        # Skip if position already at target leverage
        if self.get_json is not None:
            pos = self.position_resolver.resolve_symbol(self.get_json, symbol, category=category)
            if pos.leverage is not None and abs(pos.leverage - float(leverage)) < 1e-9:
                meta = self._meta(
                    stage, path, symbol=symbol, category=category, leverage=leverage,
                    account=self.last_account, already=True, ret_code=0, ret_msg="ALREADY_SATISFIED",
                    classification=WriteFailureClass.ALREADY_SATISFIED,
                    notes=["leverage_already_matches"],
                )
                self.last_trace.add(meta)
                return WriteResult(
                    True, path, 0, "ALREADY_SATISFIED", already_satisfied=True,
                    stage=stage.value, classification=WriteFailureClass.ALREADY_SATISFIED.value,
                    meta=meta.to_dict(),
                )

        body = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage),
        }
        return self._post_stage(stage, path, body, symbol=symbol, category=category, leverage=leverage)

    def ensure_isolated(self, symbol: str, leverage: int, *, category: str = "linear") -> WriteResult:
        """UTA/Demo: verify/set account margin mode via set-margin-mode — NEVER switch-isolated."""
        stage = WriteStage.STEP_2_VERIFY_OR_SET_MARGIN_MODE
        unsupported = "/v5/position/switch-isolated"
        # Record that classic path is forbidden on Demo
        ban = self._meta(
            stage, unsupported, symbol=symbol, category=category, leverage=leverage,
            account=self.last_account, already=False, ret_code=None, ret_msg="SKIPPED_NOT_ON_DEMO_ALLOWLIST",
            classification=WriteFailureClass.ENDPOINT_NOT_ON_DEMO_ALLOWLIST,
            notes=["demo_docs_omit_switch_isolated", "use_account_set_margin_mode"],
            demo_supported=False,
        )
        ban.notes.append("classic_switch_isolated_not_invoked")
        self.last_trace.add(ban)

        account = self.last_account or self.refresh_account_truth()
        pos = (
            self.position_resolver.resolve_symbol(self.get_json, symbol, category=category)
            if self.get_json is not None
            else DemoSymbolPositionTruth(symbol=symbol)
        )
        if self.margin_compat.already_isolated(account.margin_mode, pos.trade_mode):
            meta = self._meta(
                stage, "/v5/account/set-margin-mode", symbol=symbol, category=category,
                leverage=leverage, account=account, already=True, ret_code=0,
                ret_msg="ALREADY_ISOLATED", classification=WriteFailureClass.ALREADY_SATISFIED,
                notes=["margin_already_isolated", f"marginMode={account.margin_mode}", f"tradeMode={pos.trade_mode}"],
                margin_mode=account.margin_mode, position_idx=pos.position_idx,
            )
            self.last_trace.add(meta)
            return WriteResult(
                True, "/v5/account/set-margin-mode", 0, "ALREADY_ISOLATED",
                already_satisfied=True, stage=stage.value,
                classification=WriteFailureClass.ALREADY_SATISFIED.value, meta=meta.to_dict(),
            )

        path = "/v5/account/set-margin-mode"
        body = {"setMarginMode": "ISOLATED_MARGIN"}
        return self._post_stage(
            stage, path, body, symbol=symbol, category=category, leverage=leverage,
            margin_mode="ISOLATED_MARGIN", account=account,
        )

    def place_order(
        self,
        intent: DemoOrderIntent,
        *,
        reduce_only: bool = False,
        instrument: DemoInstrumentTruth | None = None,
        position_mode: str | None = None,
    ) -> WriteResult:
        stage = WriteStage.STEP_3_CREATE_ORDER
        blocks = self.auth.validate_order_bounds(
            symbol=intent.symbol,
            side=intent.side,
            risk_pct=0.0,
            open_positions=0,
            pending_orders=0,
        )
        blocks = [b for b in blocks if not b.startswith("risk_pct")]
        if blocks:
            return WriteResult(False, "/v5/order/create", error=";".join(blocks), stage=stage.value)

        account = self.last_account or self.refresh_account_truth()
        if account.read_only_key == 1:
            meta = self._meta(
                stage, "/v5/order/create", symbol=intent.symbol, category="linear",
                account=account, already=False, ret_code=10005,
                ret_msg="EXCHANGE_KEY_READONLY_FLAG", classification=WriteFailureClass.PERMISSION_CONTEXT_ERROR,
                notes=["query_api_readOnly=1 — exchange marks key read-only; not a missing ContractTrade checkbox"],
            )
            self.last_trace.add(meta)
            return WriteResult(
                False, "/v5/order/create", 10005, "EXCHANGE_KEY_READONLY_FLAG",
                stage=stage.value, classification=WriteFailureClass.PERMISSION_CONTEXT_ERROR.value,
                meta=meta.to_dict(), error="exchange_key_readonly_flag",
            )

        qty = intent.qty
        qty_step = instrument.qty_step if instrument else 0.0
        min_qty = instrument.min_order_qty if instrument else 0.0
        if instrument and qty_step > 0:
            qty = round_qty_to_step(qty, qty_step, min_qty)
            if qty <= 0:
                return WriteResult(
                    False, "/v5/order/create", error="qty_rounded_to_zero",
                    stage=stage.value, classification=WriteFailureClass.INVALID_QUANTITY_PRECISION.value,
                )

        idx = self.idx_resolver.resolve(
            position_mode=position_mode or (account.position_mode if account else "one_way"),
            side=intent.side,
        )
        body: dict[str, Any] = {
            "category": "linear",
            "symbol": intent.symbol,
            "side": intent.side,
            "orderType": "Market",
            "qty": self._fmt_qty(qty, qty_step),
            "timeInForce": "IOC",
            "orderLinkId": intent.client_order_id,
            "positionIdx": idx,
        }
        # Only include reduceOnly when true — some Demo contexts reject explicit false.
        if reduce_only:
            body["reduceOnly"] = True
        if intent.stop_loss_price and intent.stop_loss_price > 0 and not reduce_only:
            body["stopLoss"] = self._fmt_price(intent.stop_loss_price)
            body["slTriggerBy"] = "MarkPrice"
        if intent.take_profit_price and intent.take_profit_price > 0 and not reduce_only:
            body["takeProfit"] = self._fmt_price(intent.take_profit_price)
            body["tpTriggerBy"] = "MarkPrice"

        return self._post_stage(
            stage, "/v5/order/create", body,
            symbol=intent.symbol, category="linear", side=intent.side,
            order_type="Market", quantity=body["qty"], reduce_only=reduce_only,
            time_in_force="IOC", position_idx=idx, leverage=intent.leverage,
            order_link_id=intent.client_order_id, account=account,
            quantity_step=str(qty_step or ""), min_quantity=str(min_qty or ""),
            trigger_by=body.get("slTriggerBy"),
        )

    def set_trading_stop(
        self,
        symbol: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        position_idx: int = 0,
    ) -> WriteResult:
        stage = WriteStage.STEP_4_SET_PROTECTIVE_STOP
        body: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "positionIdx": position_idx,
            "tpslMode": "Full",
        }
        if stop_loss is not None and stop_loss > 0:
            body["stopLoss"] = self._fmt_price(stop_loss)
            body["slTriggerBy"] = "MarkPrice"
        if take_profit is not None and take_profit > 0:
            body["takeProfit"] = self._fmt_price(take_profit)
            body["tpTriggerBy"] = "MarkPrice"
        return self._post_stage(
            stage, "/v5/position/trading-stop", body,
            symbol=symbol, category="linear", position_idx=position_idx,
            trigger_by="MarkPrice",
        )

    def cancel_order(self, symbol: str, *, order_id: str | None = None, order_link_id: str | None = None) -> WriteResult:
        body: dict[str, Any] = {"category": "linear", "symbol": symbol}
        if order_id:
            body["orderId"] = order_id
        if order_link_id:
            body["orderLinkId"] = order_link_id
        return self._post_stage(
            WriteStage.STEP_6_CANCEL_ORDER, "/v5/order/cancel", body,
            symbol=symbol, category="linear",
        )

    def close_position(self, symbol: str, side: str, qty: float) -> WriteResult:
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
        # Reuse create with reduceOnly; stage label overridden after
        res = self.place_order(intent, reduce_only=True)
        res.stage = WriteStage.STEP_7_CLOSE_POSITION.value
        return res

    # ── internals ──────────────────────────────────────────────────────────

    def _fmt_qty(self, qty: float, step: float) -> str:
        if step > 0:
            decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
            return f"{qty:.{decimals}f}"
        s = f"{qty:.8f}".rstrip("0").rstrip(".")
        return s or "0"

    def _fmt_price(self, price: float) -> str:
        s = f"{price:.8f}".rstrip("0").rstrip(".")
        return s or "0"

    def _meta(
        self,
        stage: WriteStage,
        path: str,
        *,
        symbol: str | None = None,
        category: str | None = None,
        leverage: int | None = None,
        side: str | None = None,
        order_type: str | None = None,
        quantity: str | None = None,
        reduce_only: bool | None = None,
        time_in_force: str | None = None,
        position_idx: int | None = None,
        margin_mode: str | None = None,
        account: DemoAccountModeTruth | None = None,
        already: bool = False,
        ret_code: int | None = None,
        ret_msg: str | None = None,
        classification: WriteFailureClass = WriteFailureClass.OK,
        notes: list[str] | None = None,
        demo_supported: bool | None = None,
        order_link_id: str | None = None,
        quantity_step: str | None = None,
        min_quantity: str | None = None,
        trigger_by: str | None = None,
    ) -> DemoWriteRequestMetadata:
        if demo_supported is None:
            if path in DEMO_UNSUPPORTED_WRITE_PATHS:
                demo_supported = False
            else:
                demo_supported = path in DEMO_SUPPORTED_WRITE_PATHS
        return DemoWriteRequestMetadata(
            stage=stage,
            method="POST",
            endpoint_path=path,
            category=category,
            symbol=symbol,
            account_type=account.account_type if account else None,
            position_mode=account.position_mode if account else None,
            position_idx=position_idx,
            margin_mode=margin_mode or (account.margin_mode if account else None),
            leverage=leverage,
            side=side,
            order_type=order_type,
            quantity=quantity,
            quantity_step=quantity_step,
            min_quantity=min_quantity,
            reduce_only=reduce_only,
            trigger_by=trigger_by,
            time_in_force=time_in_force,
            order_link_id_hash=hash_order_link_id(order_link_id) if order_link_id else None,
            timestamp_ms=int(time.time() * 1000),
            ret_code=ret_code,
            ret_msg=ret_msg,
            already_satisfied=already,
            demo_endpoint_supported=demo_supported,
            classification=classification,
            notes=list(notes or []),
        )

    def _post_stage(
        self,
        stage: WriteStage,
        path: str,
        body: dict[str, Any],
        **kwargs: Any,
    ) -> WriteResult:
        account = kwargs.pop("account", self.last_account)
        order_link_id = kwargs.pop("order_link_id", None)
        try:
            resp = self.transport.post(path, body)
        except Exception as exc:  # noqa: BLE001
            classification = WriteFailureClass.AMBIGUOUS_TIMEOUT if "Timeout" in type(exc).__name__ else WriteFailureClass.UNKNOWN_EXCHANGE_ERROR
            meta = self._meta(
                stage, path, account=account, already=False, ret_code=-1,
                ret_msg=type(exc).__name__, classification=classification,
                notes=[f"transport_error:{type(exc).__name__}"], order_link_id=order_link_id, **kwargs,
            )
            self.last_trace.add(meta)
            return WriteResult(
                False, path, error=type(exc).__name__, stage=stage.value,
                classification=classification.value, meta=meta.to_dict(),
            )

        ret = int(resp.get("retCode", -1))
        ret_msg = str(resp.get("retMsg") or "")
        classification = self.classifier.classify(
            stage=stage, endpoint_path=path, ret_code=ret, ret_msg=ret_msg,
            account_type=account.account_type if account else None,
            margin_mode=account.margin_mode if account else None,
        )
        already = classification == WriteFailureClass.ALREADY_SATISFIED
        ok = ret == 0 or already
        result = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        order_id = None
        if isinstance(result, dict):
            order_id = result.get("orderId") or result.get("orderLinkId")
        meta = self._meta(
            stage, path, account=account, already=already, ret_code=ret, ret_msg=ret_msg,
            classification=classification, order_link_id=order_link_id, **kwargs,
        )
        self.last_trace.add(meta)
        return WriteResult(
            ok=ok,
            path=path,
            ret_code=ret,
            ret_msg=ret_msg,
            order_id=str(order_id) if order_id else None,
            dry_run=bool(result.get("dryRun")) if isinstance(result, dict) else False,
            already_satisfied=already,
            stage=stage.value,
            classification=classification.value,
            meta=meta.to_dict(),
            raw_safe={"retCode": ret, "retMsg": ret_msg[:120], "hasResult": bool(result)},
        )
