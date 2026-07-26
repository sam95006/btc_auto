"""Resolve Demo UTA account / position / margin mode from exchange truth."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class DemoAccountModeTruth:
    account_type: str = "UNIFIED"
    unified_margin_status: str | None = None
    margin_mode: str | None = None  # ISOLATED_MARGIN | REGULAR_MARGIN | PORTFOLIO_MARGIN
    position_mode: str | None = None  # one_way | hedge
    unified_account_status: int | None = None
    read_only_key: int | None = None  # 0 = R/W, 1 = read-only (from query-api)
    contract_trade_order: bool = False
    contract_trade_position: bool = False
    uta: int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accountType": self.account_type,
            "unifiedMarginStatus": self.unified_margin_status,
            "marginMode": self.margin_mode,
            "positionMode": self.position_mode,
            "unifiedAccountStatus": self.unified_account_status,
            "readOnlyKey": self.read_only_key,
            "contractTradeOrder": self.contract_trade_order,
            "contractTradePosition": self.contract_trade_position,
            "uta": self.uta,
            "notes": list(self.notes),
            "secretSafe": True,
        }


@dataclass
class DemoSymbolPositionTruth:
    symbol: str
    size: float = 0.0
    side: str = ""
    leverage: float | None = None
    trade_mode: int | None = None  # 0 cross / 1 isolated when present
    position_idx: int = 0
    liq_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "size": self.size,
            "side": self.side,
            "leverage": self.leverage,
            "tradeMode": self.trade_mode,
            "positionIdx": self.position_idx,
            "liqPrice": self.liq_price,
        }


@dataclass
class DemoInstrumentTruth:
    symbol: str
    category: str = "linear"
    status: str = ""
    max_leverage: float = 0.0
    qty_step: float = 0.0
    min_order_qty: float = 0.0
    min_notional: float = 0.0
    tick_size: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "category": self.category,
            "status": self.status,
            "maxLeverage": self.max_leverage,
            "qtyStep": self.qty_step,
            "minOrderQty": self.min_order_qty,
            "minNotionalValue": self.min_notional,
            "tickSize": self.tick_size,
        }


GetJson = Callable[[str, dict[str, Any] | None], dict[str, Any]]


class DemoAccountModeResolver:
    """GET-only truth: account/info + query-api permissions (values redacted)."""

    def resolve(self, get_json: GetJson) -> DemoAccountModeTruth:
        truth = DemoAccountModeTruth()
        # query-api
        try:
            qa = get_json("/v5/user/query-api", None)
            result = qa.get("result") if isinstance(qa.get("result"), dict) else {}
            truth.read_only_key = int(result.get("readOnly")) if result.get("readOnly") is not None else None
            truth.uta = int(result.get("uta")) if result.get("uta") is not None else None
            perms = result.get("permissions") or {}
            if isinstance(perms, dict):
                ct = perms.get("ContractTrade") or []
                truth.contract_trade_order = "Order" in ct
                truth.contract_trade_position = "Position" in ct
            if truth.read_only_key == 1:
                truth.notes.append("query_api_readOnly=1_exchange_marks_key_readonly")
            if truth.read_only_key == 0:
                truth.notes.append("query_api_readOnly=0_read_write_key")
        except Exception as exc:  # noqa: BLE001
            truth.notes.append(f"query_api_failed:{type(exc).__name__}")

        # account/info
        try:
            info = get_json("/v5/account/info", None)
            result = info.get("result") if isinstance(info.get("result"), dict) else {}
            truth.margin_mode = str(result.get("marginMode") or result.get("marginModeName") or "") or None
            # unifiedMarginStatus: 1 classic→UTA etc.
            ums = result.get("unifiedMarginStatus")
            truth.unified_margin_status = str(ums) if ums is not None else None
            # position mode sometimes on account info
            pm = result.get("positionMode")
            if pm is not None:
                # 0 both sides / one-way depending on docs — store raw then map
                truth.position_mode = "hedge" if int(pm) == 3 else "one_way"
            truth.account_type = "UNIFIED"
            if not truth.margin_mode:
                truth.notes.append("account_info_margin_mode_missing")
        except Exception as exc:  # noqa: BLE001
            truth.notes.append(f"account_info_failed:{type(exc).__name__}")
            truth.notes.append("fallback_assume_UNIFIED")

        return truth


class DemoPositionModeResolver:
    def resolve_symbol(
        self,
        get_json: GetJson,
        symbol: str,
        *,
        category: str = "linear",
    ) -> DemoSymbolPositionTruth:
        out = DemoSymbolPositionTruth(symbol=symbol)
        try:
            resp = get_json(
                "/v5/position/list",
                {"category": category, "symbol": symbol},
            )
            rows = ((resp.get("result") or {}).get("list") or []) if isinstance(resp, dict) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("symbol") or "") != symbol:
                    continue
                size = float(row.get("size") or 0)
                out.size = size
                out.side = str(row.get("side") or "")
                try:
                    out.leverage = float(row.get("leverage") or 0) or None
                except (TypeError, ValueError):
                    out.leverage = None
                try:
                    out.trade_mode = int(row.get("tradeMode")) if row.get("tradeMode") is not None else None
                except (TypeError, ValueError):
                    out.trade_mode = None
                try:
                    out.position_idx = int(row.get("positionIdx") or 0)
                except (TypeError, ValueError):
                    out.position_idx = 0
                try:
                    lp = row.get("liqPrice")
                    out.liq_price = float(lp) if lp not in (None, "", "0", "0.00") else None
                except (TypeError, ValueError):
                    out.liq_price = None
                break
        except Exception:
            pass
        return out


class DemoPositionIndexResolver:
    """Map one-way / hedge to positionIdx for linear USDT perp."""

    def resolve(self, *, position_mode: str | None, side: str) -> int:
        mode = (position_mode or "one_way").lower()
        if mode in ("one_way", "oneway", "merged_single", "0"):
            return 0
        # hedge
        if side in ("Buy", "LONG", "Long"):
            return 1
        return 2


class DemoMarginModeCompatibility:
    """Demo UTA: prefer account set-margin-mode; never switch-isolated."""

    TARGET = "ISOLATED_MARGIN"

    def needs_switch(self, current: str | None) -> bool:
        if not current:
            return True
        return current.upper() not in {self.TARGET, "ISOLATED"}

    def already_isolated(self, current: str | None, trade_mode: int | None) -> bool:
        if current and current.upper() in {self.TARGET, "ISOLATED"}:
            return True
        if trade_mode == 1:
            return True
        return False
