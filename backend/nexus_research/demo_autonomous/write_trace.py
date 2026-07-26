"""Safe write-stage tracing + 10005 classification (no secrets)."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WriteStage(str, Enum):
    STEP_1_SET_LEVERAGE = "STEP_1_SET_LEVERAGE"
    STEP_2_VERIFY_OR_SET_MARGIN_MODE = "STEP_2_VERIFY_OR_SET_MARGIN_MODE"
    STEP_3_CREATE_ORDER = "STEP_3_CREATE_ORDER"
    STEP_4_SET_PROTECTIVE_STOP = "STEP_4_SET_PROTECTIVE_STOP"
    STEP_5_SET_TAKE_PROFIT = "STEP_5_SET_TAKE_PROFIT"
    STEP_6_CANCEL_ORDER = "STEP_6_CANCEL_ORDER"
    STEP_7_CLOSE_POSITION = "STEP_7_CLOSE_POSITION"
    PREFLIGHT_ACCOUNT_TRUTH = "PREFLIGHT_ACCOUNT_TRUTH"


class WriteFailureClass(str, Enum):
    PERMISSION_CONTEXT_ERROR = "PERMISSION_CONTEXT_ERROR"
    ENDPOINT_NOT_SUPPORTED_IN_ACCOUNT_MODE = "ENDPOINT_NOT_SUPPORTED_IN_ACCOUNT_MODE"
    ENDPOINT_NOT_ON_DEMO_ALLOWLIST = "ENDPOINT_NOT_ON_DEMO_ALLOWLIST"
    WRONG_CATEGORY = "WRONG_CATEGORY"
    WRONG_POSITION_INDEX = "WRONG_POSITION_INDEX"
    WRONG_MARGIN_MODE_OPERATION = "WRONG_MARGIN_MODE_OPERATION"
    INVALID_QUANTITY_PRECISION = "INVALID_QUANTITY_PRECISION"
    MIN_NOTIONAL_FAILURE = "MIN_NOTIONAL_FAILURE"
    LEVERAGE_CONFIGURATION_FAILURE = "LEVERAGE_CONFIGURATION_FAILURE"
    SIGNATURE_FAILURE = "SIGNATURE_FAILURE"
    TIMESTAMP_FAILURE = "TIMESTAMP_FAILURE"
    RATE_LIMIT = "RATE_LIMIT"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    ORDER_REJECTED = "ORDER_REJECTED"
    PROTECTION_REJECTED = "PROTECTION_REJECTED"
    AMBIGUOUS_TIMEOUT = "AMBIGUOUS_TIMEOUT"
    ALREADY_SATISFIED = "ALREADY_SATISFIED"
    UNKNOWN_EXCHANGE_ERROR = "UNKNOWN_EXCHANGE_ERROR"
    OK = "OK"


# Official Demo Trading available write endpoints (Bybit docs).
DEMO_SUPPORTED_WRITE_PATHS = frozenset({
    "/v5/order/create",
    "/v5/order/amend",
    "/v5/order/cancel",
    "/v5/order/cancel-all",
    "/v5/order/create-batch",
    "/v5/order/amend-batch",
    "/v5/order/cancel-batch",
    "/v5/position/set-leverage",
    "/v5/position/switch-mode",
    "/v5/position/trading-stop",
    "/v5/position/set-auto-add-margin",
    "/v5/position/add-margin",
    "/v5/account/set-margin-mode",
    "/v5/account/set-collateral-switch",
    "/v5/account/set-hedging-mode",
})

# Explicitly NOT on Demo allowlist (classic-account paths).
DEMO_UNSUPPORTED_WRITE_PATHS = frozenset({
    "/v5/position/switch-isolated",
})


@dataclass
class DemoWriteRequestMetadata:
    stage: WriteStage
    method: str
    endpoint_path: str
    domain: str = "api-demo.bybit.com"
    category: str | None = None
    symbol: str | None = None
    account_type: str | None = None
    position_mode: str | None = None
    position_idx: int | None = None
    margin_mode: str | None = None
    leverage: int | None = None
    side: str | None = None
    order_type: str | None = None
    quantity: str | None = None
    quantity_step: str | None = None
    min_quantity: str | None = None
    min_notional: str | None = None
    reduce_only: bool | None = None
    close_on_trigger: bool | None = None
    trigger_by: str | None = None
    time_in_force: str | None = None
    order_link_id_hash: str | None = None
    timestamp_ms: int = 0
    recv_window: str = "5000"
    ret_code: int | None = None
    ret_msg: str | None = None
    already_satisfied: bool = False
    demo_endpoint_supported: bool | None = None
    classification: WriteFailureClass = WriteFailureClass.OK
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "method": self.method,
            "endpointPath": self.endpoint_path,
            "domain": self.domain,
            "category": self.category,
            "symbol": self.symbol,
            "accountType": self.account_type,
            "positionMode": self.position_mode,
            "positionIdx": self.position_idx,
            "marginMode": self.margin_mode,
            "leverage": self.leverage,
            "side": self.side,
            "orderType": self.order_type,
            "quantity": self.quantity,
            "quantityStep": self.quantity_step,
            "minQuantity": self.min_quantity,
            "minNotional": self.min_notional,
            "reduceOnly": self.reduce_only,
            "closeOnTrigger": self.close_on_trigger,
            "triggerBy": self.trigger_by,
            "timeInForce": self.time_in_force,
            "orderLinkIdHash": self.order_link_id_hash,
            "timestampMs": self.timestamp_ms,
            "recvWindow": self.recv_window,
            "retCode": self.ret_code,
            "retMsg": (self.ret_msg or "")[:160],
            "alreadySatisfied": self.already_satisfied,
            "demoEndpointSupported": self.demo_endpoint_supported,
            "classification": self.classification.value,
            "notes": list(self.notes),
            "secretSafe": True,
        }


def hash_order_link_id(order_link_id: str) -> str:
    return hashlib.sha256(order_link_id.encode("utf-8")).hexdigest()[:16]


class BybitDemoErrorClassifier:
    """Classify Demo write failures without treating all 10005 as user-key issues."""

    def classify(
        self,
        *,
        stage: WriteStage,
        endpoint_path: str,
        ret_code: int,
        ret_msg: str = "",
        account_type: str | None = None,
        margin_mode: str | None = None,
    ) -> WriteFailureClass:
        msg = (ret_msg or "").lower()
        if ret_code == 0:
            return WriteFailureClass.OK
        if endpoint_path in DEMO_UNSUPPORTED_WRITE_PATHS:
            return WriteFailureClass.ENDPOINT_NOT_ON_DEMO_ALLOWLIST
        if ret_code == 10005 and endpoint_path in DEMO_UNSUPPORTED_WRITE_PATHS:
            return WriteFailureClass.ENDPOINT_NOT_ON_DEMO_ALLOWLIST
        if ret_code == 10005 and endpoint_path not in DEMO_SUPPORTED_WRITE_PATHS:
            return WriteFailureClass.ENDPOINT_NOT_ON_DEMO_ALLOWLIST
        if ret_code == 10004:
            return WriteFailureClass.SIGNATURE_FAILURE
        if ret_code == 10002:
            return WriteFailureClass.TIMESTAMP_FAILURE
        if ret_code in (10006, 10018):
            return WriteFailureClass.RATE_LIMIT
        if ret_code == 110043 or "not been modified" in msg or "leverage not modified" in msg:
            return WriteFailureClass.ALREADY_SATISFIED
        if ret_code == 34040 or msg.strip() == "not modified":
            return WriteFailureClass.ALREADY_SATISFIED
        if ret_code in (110001, 110003, 110004) or "qty" in msg or "precision" in msg:
            return WriteFailureClass.INVALID_QUANTITY_PRECISION
        if "notional" in msg or ret_code == 110092:
            return WriteFailureClass.MIN_NOTIONAL_FAILURE
        if "position idx" in msg or "positionidx" in msg or ret_code in (10001,) and "idx" in msg:
            return WriteFailureClass.WRONG_POSITION_INDEX
        if "margin" in msg and stage == WriteStage.STEP_2_VERIFY_OR_SET_MARGIN_MODE:
            return WriteFailureClass.WRONG_MARGIN_MODE_OPERATION
        if ret_code in (110012, 110014) or "balance" in msg:
            return WriteFailureClass.INSUFFICIENT_BALANCE
        if stage == WriteStage.STEP_4_SET_PROTECTIVE_STOP and ret_code != 0:
            return WriteFailureClass.PROTECTION_REJECTED
        if ret_code == 10005:
            # Exchange-level permission OR unsupported-in-context; not auto "user forgot Order perm".
            if account_type == "UNIFIED" and endpoint_path == "/v5/position/switch-isolated":
                return WriteFailureClass.ENDPOINT_NOT_SUPPORTED_IN_ACCOUNT_MODE
            return WriteFailureClass.PERMISSION_CONTEXT_ERROR
        if stage == WriteStage.STEP_3_CREATE_ORDER:
            return WriteFailureClass.ORDER_REJECTED
        return WriteFailureClass.UNKNOWN_EXCHANGE_ERROR


@dataclass
class DemoWriteStageTrace:
    stages: list[DemoWriteRequestMetadata] = field(default_factory=list)
    root_stage: WriteStage | None = None
    root_classification: WriteFailureClass | None = None

    def add(self, meta: DemoWriteRequestMetadata) -> None:
        self.stages.append(meta)
        if meta.ret_code not in (None, 0) and not meta.already_satisfied and self.root_stage is None:
            self.root_stage = meta.stage
            self.root_classification = meta.classification

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": [s.to_dict() for s in self.stages],
            "rootStage": self.root_stage.value if self.root_stage else None,
            "rootClassification": self.root_classification.value if self.root_classification else None,
            "secretSafe": True,
        }

    def root_cause_report(self) -> dict[str, Any]:
        fail = next((s for s in self.stages if s.stage == self.root_stage), None)
        if fail is None:
            return {
                "failed_stage": None,
                "failed_endpoint": None,
                "retCode": 0,
                "root_cause_classification": WriteFailureClass.OK.value,
                "credential_issue_excluded": True,
            }
        return {
            "failed_stage": fail.stage.value,
            "failed_endpoint": fail.endpoint_path,
            "category": fail.category,
            "account_type": fail.account_type,
            "position_mode": fail.position_mode,
            "positionIdx": fail.position_idx,
            "margin_mode": fail.margin_mode,
            "request_payload_valid": fail.classification
            not in (
                WriteFailureClass.INVALID_QUANTITY_PRECISION,
                WriteFailureClass.MIN_NOTIONAL_FAILURE,
                WriteFailureClass.WRONG_CATEGORY,
            ),
            "instrument_metadata_valid": True,
            "signature_context_valid": fail.classification != WriteFailureClass.SIGNATURE_FAILURE,
            "retCode": fail.ret_code,
            "retMsg": (fail.ret_msg or "")[:160],
            "root_cause_classification": fail.classification.value,
            "credential_issue_excluded": fail.classification
            != WriteFailureClass.PERMISSION_CONTEXT_ERROR
            or fail.endpoint_path in DEMO_UNSUPPORTED_WRITE_PATHS,
            "demoEndpointSupported": fail.demo_endpoint_supported,
            "notes": list(fail.notes),
            "capturedAtMs": int(time.time() * 1000),
            "secretSafe": True,
        }
