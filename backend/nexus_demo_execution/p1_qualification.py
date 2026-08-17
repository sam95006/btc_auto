"""Founder-approved one-shot Bybit Demo P1 qualification lifecycle.

Requires FOUNDER_P1_APPROVED=true and P1_GO=RUN_ONE_BYBIT_DEMO_TRADE.
Does not start autonomous trading and never treats a create acknowledgement as a fill.
"""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError, _round_qty
from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger, OrderIntent
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.kill_switch import KillSwitch
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler, exchange_state
from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from backend.nexus_demo_execution.wallet_lifecycle_accounting import (
    build_lifecycle_accounting_record,
    classify_pnl_provenance,
)


P1_GO_PHRASE = "RUN_ONE_BYBIT_DEMO_TRADE"
P1_CAMPAIGN_ID = "bybit-demo-p1-qualification"
P1_SYMBOLS = ("BTCUSDT", "ETHUSDT")
TICKER_MAX_AGE_MS = 15_000
SERVER_TIME_BRACKET_MAX_MS = 5_000
FILL_TIMEOUT_SEC = 45
CLOSE_TIMEOUT_SEC = 45
POLL_INTERVAL_SEC = 1.0
PROTECTIVE_SL_PCT = 0.03
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
SECRET_ENV_KEYS = (
    "BYBIT_DEMO_API_KEY",
    "BYBIT_DEMO_API_SECRET",
    "NEXUS_STAGING_POSTGRES_URL",
    "NEXUS_POSTGRES_URL",
    "DATABASE_URL",
)
DISARMED_FLAGS = {
    "MAINNET": "false",
    "REAL_MONEY": "false",
    "DEMO_AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SEND": "false",
    "EXCHANGE_WRITE": "false",
    "NEXUS_AUTONOMOUS_DEMO_AUTO_SEND": "false",
}


def _flag_true(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in TRUE_VALUES


def _authorized() -> bool:
    return _flag_true("FOUNDER_P1_APPROVED") and (os.environ.get("P1_GO") or "").strip() == P1_GO_PHRASE


def _safe_prefix(value: Any, n: int = 8) -> str:
    text = str(value or "")
    if not text:
        return ""
    return text[:n]


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _full(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _postgres_url() -> str:
    return (os.environ.get("NEXUS_POSTGRES_URL") or os.environ.get("DATABASE_URL") or "").strip()


def _smallest_qty(client: Any, info: dict[str, Any], price: float) -> str:
    step = float(client.qty_step(info))
    min_q = float(client.min_qty(info))
    min_n = float(client.min_notional(info))
    qty = max(min_q, step)
    if min_n > 0 and price > 0 and qty * price + 1e-12 < min_n:
        qty = math.ceil((min_n / price) / step - 1e-12) * step
    qty_str = _round_qty(qty, step)
    qty_f = float(qty_str or "0")
    if qty_f <= 0:
        raise DemoWriteError("qty_invalid", "smallest_qty_zero")
    if min_q > 0 and qty_f + 1e-15 < min_q:
        raise DemoWriteError("qty_below_min", qty_str)
    if min_n > 0 and qty_f * price + 1e-12 < min_n:
        raise DemoWriteError("notional_below_min", f"{qty_f * price}<{min_n}")
    return qty_str


def _protective_prices(client: DemoWriteClient, *, side: str, price: float, info: dict[str, Any]) -> tuple[str, str]:
    tick = client.tick_size(info)
    if side == "Buy":
        sl = price * (1.0 - PROTECTIVE_SL_PCT)
        tp = price * (1.0 + PROTECTIVE_SL_PCT)
    else:
        sl = price * (1.0 + PROTECTIVE_SL_PCT)
        tp = price * (1.0 - PROTECTIVE_SL_PCT)
    return client.format_price(sl, tick), client.format_price(tp, tick)


def _history_states(rows: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("to_state") or "") for item in rows]


def _has_lifecycle(states: list[str]) -> bool:
    required = ["INTENT_CREATED", "SUBMITTING", "FILLED", "CLOSE_PENDING", "CLOSED"]
    idx = 0
    for item in states:
        if item == required[idx]:
            idx += 1
            if idx == len(required):
                return True
    return False


def _accepted_or_new_present(states: list[str]) -> bool:
    return "ACCEPTED" in states or "NEW" in states


def _match_closed_pnl(
    rows: list[dict[str, Any]],
    *,
    close_order_id: str,
    entry_order_id: str,
    close_link_id: str,
) -> dict[str, Any] | None:
    """Bind closed PnL only to this qualification's order identities. Never newest-row fallback."""
    wanted_ids = {item for item in (str(close_order_id or ""), str(entry_order_id or "")) if item}
    wanted_link = str(close_link_id or "")
    for row in rows:
        oid = str(row.get("orderId") or "")
        if oid and oid in wanted_ids:
            return row
        link = str(row.get("orderLinkId") or "")
        if wanted_link and link == wanted_link:
            return row
    return None


@dataclass
class P1QualificationRunner:
    client: Any
    ledger: Any
    reconciler: BybitDemoReconciler | None = None
    sleep: Callable[[float], None] = time.sleep
    now_ms: Callable[[], int] = _now_ms
    apply_pending_schema: Callable[[], dict[str, Any]] | None = None
    time_fn: Callable[[], float] = time.time
    fill_timeout_sec: float = FILL_TIMEOUT_SEC
    close_timeout_sec: float = CLOSE_TIMEOUT_SEC
    create_order_calls: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.reconciler is None:
            self.reconciler = BybitDemoReconciler(self.ledger, self.client)

    def run(self) -> dict[str, Any]:
        self.evidence = self._base_evidence()
        try:
            if not _authorized():
                self.evidence["error"] = "authorization_missing"
                self.evidence["create_order_calls"] = 0
                return self._finalize(hold_reason="authorization_missing")
            preflight = self.preflight()
            self.evidence["preflight"] = preflight
            if not preflight.get("ok"):
                self.evidence["error"] = preflight.get("reason") or "preflight_failed"
                return self._finalize(hold_reason=self.evidence["error"])
            return self._execute_lifecycle(preflight)
        except Exception as exc:  # noqa: BLE001
            self.evidence["error"] = f"{type(exc).__name__}:{exc}"
            self.evidence["fail_closed"] = True
            return self._finalize(hold_reason=self.evidence["error"])

    def preflight(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": False}
        key_present = bool((os.environ.get("BYBIT_DEMO_API_KEY") or "").strip() or getattr(self.client, "api_key", ""))
        secret_present = bool(
            (os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip() or getattr(self.client, "api_secret", "")
        )
        self.evidence["BYBIT_DEMO_SECRET_BOUNDARY_PASS"] = bool(key_present and secret_present)
        result["secret_key_present"] = key_present
        result["secret_secret_present"] = secret_present
        if not (key_present and secret_present):
            result["reason"] = "credentials_missing"
            return result

        base = str(getattr(self.client, "base_url", "") or DEMO_REST_BASE_URL).rstrip("/")
        if base != DEMO_REST_BASE_URL.rstrip("/") or "api-demo.bybit.com" not in base:
            result["reason"] = "bybit_host_rejected"
            return result
        if _flag_true("MAINNET") or _flag_true("REAL_MONEY"):
            result["reason"] = "safety_flag_armed"
            return result

        gate = DemoExecutionSafetyGate()
        kill = KillSwitch(gate)
        blocked = kill.check_triggers(
            {
                "mainnet_detected": _flag_true("MAINNET"),
                "real_money": _flag_true("REAL_MONEY"),
                "founder_smoke_authorized": True,
                "unauthorized_exchange_write": False,
            }
        )
        self.evidence["PRE_ENTRY_KILL_SWITCH_PASS"] = not blocked and not kill.engaged
        if blocked or kill.engaged:
            result["reason"] = "kill_switch_engaged"
            result["kill_switch"] = kill.snapshot()
            return result

        if self.apply_pending_schema is not None:
            applied = self.apply_pending_schema()
            result["schema_apply"] = {"ok": bool(applied.get("ok")), "applied": applied.get("applied") or []}
            if applied.get("ok") is False:
                result["reason"] = "schema_apply_failed"
                return result

        migrations = self.ledger.required_migrations_present()
        result["migrations"] = migrations
        probe = self.ledger.probe_write_read()
        result["ledger_probe"] = {"ok": bool(probe.get("ok"))}
        ledger_ok = bool(migrations.get("ok") and migrations.get("migration_0005_present") and probe.get("ok"))
        self.evidence["BYBIT_DEMO_P1_LEDGER_CONNECTION_PASS"] = ledger_ok
        if not ledger_ok:
            result["reason"] = "ledger_unavailable"
            return result

        startup = self.reconciler.startup_reconcile() if self.reconciler else {"entries_allowed": False}
        open_orders = list(self.client.list_open_orders() or [])
        positions = list(self.client.list_positions() or [])
        unfinished = list(self.ledger.unfinished())
        recon_ok = (
            bool(startup.get("entries_allowed"))
            and not open_orders
            and not positions
            and not unfinished
            and int(startup.get("orphan_positions") or 0) == 0
            and int(startup.get("unresolved_intents") or 0) == 0
        )
        self.evidence["PRE_ENTRY_RECONCILIATION_PASS"] = recon_ok
        result["startup_reconcile"] = {
            "entries_allowed": bool(startup.get("entries_allowed")),
            "unresolved_intents": int(startup.get("unresolved_intents") or 0),
            "orphan_positions": int(startup.get("orphan_positions") or 0),
            "open_orders": len(open_orders),
            "open_positions": len(positions),
            "unfinished_intents": len(unfinished),
        }
        if not recon_ok:
            result["reason"] = "startup_reconciliation_blocked"
            return result

        account = self.client.fetch_account_identity()
        wallet = self.client.fetch_wallet_snapshot()
        result["account_uid_present"] = bool(account.get("account_uid") or account.get("api_key_fingerprint"))
        result["wallet_source"] = wallet.get("source_endpoint")
        market = self._fresh_market()
        result["market"] = {k: market[k] for k in ("symbol", "last_price", "fresh", "reason") if k in market}
        for key in (
            "market_freshness_source",
            "ticker_envelope_time_present",
            "server_time_before_present",
            "server_time_after_present",
            "server_time_bracket_ms",
        ):
            if key in market:
                self.evidence[key] = market[key]
        if market.get("symbol"):
            self.evidence["market_symbol"] = market["symbol"]
        self.evidence["FRESH_OFFICIAL_EXECUTION_DATA_PASS"] = bool(market.get("fresh"))
        self.evidence["NO_MOCK_EXECUTION_PRICE_PASS"] = bool(market.get("fresh")) and market.get("last_price", 0) > 0
        if not market.get("fresh"):
            result["reason"] = market.get("reason") or "stale_or_missing_market_data"
            return result

        qty = _smallest_qty(self.client, market["info"], market["last_price"])
        notional = float(qty) * float(market["last_price"])
        margin = notional / float(FIXED_LEVERAGE)
        risk_ok = 0 < margin <= MARGIN_PER_TRADE_CAP and 0 < notional <= (MARGIN_PER_TRADE_CAP * FIXED_LEVERAGE)
        self.evidence["RISK_ENGINE_FINAL_AUTHORITY_PASS"] = risk_ok
        result["qty"] = qty
        result["notional"] = notional
        result["margin_usdt"] = margin
        result["symbol"] = market["symbol"]
        result["side"] = "Buy"
        result["last_price"] = market["last_price"]
        result["info"] = market["info"]
        result["wallet_before"] = wallet
        result["account"] = account
        if not risk_ok:
            result["reason"] = "risk_cap_exceeded"
            return result

        result["ok"] = True
        self.evidence["P1_PREFLIGHT_PASS"] = True
        return result

    def _fresh_market(self) -> dict[str, Any]:
        now = self.now_ms()
        last_error = "ticker_unavailable"
        for symbol in P1_SYMBOLS:
            try:
                ticker = self.client.fetch_ticker(symbol)
                last = float(ticker.get("lastPrice") or ticker.get("markPrice") or 0)
                ticker_time = int(float(ticker.get("time") or 0))
                if last <= 0:
                    last_error = f"{symbol}:price_missing"
                    continue
                if ticker_time > 0:
                    age = now - ticker_time
                    if age < 0 or age > TICKER_MAX_AGE_MS:
                        last_error = f"{symbol}:stale_ticker:{age}"
                        continue
                    freshness = {
                        "market_freshness_source": "BYBIT_TICKER_ENVELOPE_TIME",
                        "ticker_envelope_time_present": True,
                        "ticker_time": ticker_time,
                        "age_ms": age,
                    }
                else:
                    server_before = int(self.client.fetch_server_time())
                    # Re-read the ticker inside the official server-time bracket.
                    ticker = self.client.fetch_ticker(symbol)
                    last = float(ticker.get("lastPrice") or ticker.get("markPrice") or 0)
                    server_after = int(self.client.fetch_server_time())
                    bracket = server_after - server_before
                    if last <= 0:
                        last_error = f"{symbol}:price_missing"
                        continue
                    if server_before <= 0 or server_after <= 0 or bracket < 0 or bracket > SERVER_TIME_BRACKET_MAX_MS:
                        last_error = f"{symbol}:server_time_bracket_invalid:{bracket}"
                        continue
                    freshness = {
                        "market_freshness_source": "BYBIT_SERVER_TIME_BRACKET",
                        "ticker_envelope_time_present": False,
                        "server_time_before_present": True,
                        "server_time_after_present": True,
                        "server_time_bracket_ms": bracket,
                    }
                info = self.client.fetch_instrument(symbol)
                return {
                    "fresh": True,
                    "symbol": symbol,
                    "last_price": last,
                    "info": info,
                    "ticker": ticker,
                    **freshness,
                }
            except DemoWriteError as exc:
                last_error = f"{symbol}:{exc.code}"
            except Exception as exc:  # noqa: BLE001
                last_error = f"{symbol}:{type(exc).__name__}"
        return {"fresh": False, "reason": last_error}

    def _execute_lifecycle(self, preflight: dict[str, Any]) -> dict[str, Any]:
        symbol = str(preflight["symbol"])
        side = str(preflight["side"])
        qty = str(preflight["qty"])
        price = float(preflight["last_price"])
        info = preflight["info"]
        decision_id = f"p1dec_{uuid.uuid4().hex[:16]}"
        trade_id = f"p1trd_{uuid.uuid4().hex[:16]}"
        entry_intent_id = f"p1ent_{uuid.uuid4().hex[:16]}"
        sl, tp = _protective_prices(self.client, side=side, price=price, info=info)

        entry_intent = OrderIntent(
            order_intent_id=entry_intent_id,
            decision_id=decision_id,
            trade_id=trade_id,
            campaign_id=P1_CAMPAIGN_ID,
            symbol=symbol,
            side=side,
            requested_qty=_d(qty),
            order_type="Market",
        )
        order_link_id = self.ledger.create_intent(entry_intent)
        self.evidence["decision_id_prefix"] = _safe_prefix(decision_id)
        self.evidence["trade_id_prefix"] = _safe_prefix(trade_id)
        self.evidence["order_intent_id_prefix"] = _safe_prefix(entry_intent_id)
        self.evidence["orderLinkId_prefix"] = _safe_prefix(order_link_id)
        self.ledger.transition(entry_intent_id, "SUBMITTING", source="p1_pre_submit")

        try:
            if getattr(self.client, "set_leverage", None):
                self.client.set_leverage(symbol, FIXED_LEVERAGE)
            self.create_order_calls += 1
            create_resp = self.client.create_market_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_link_id=order_link_id,
                stop_loss=sl,
                take_profit=tp,
            )
        except Exception as exc:  # noqa: BLE001
            self.ledger.transition(
                entry_intent_id,
                "SUBMIT_UNKNOWN",
                source="bybit_create_error",
                exchange={"reject_reason": type(exc).__name__},
            )
            self.evidence["error"] = f"entry_submit_unknown:{type(exc).__name__}"
            self.evidence["orphan_or_unresolved"] = True
            return self._finalize(hold_reason=self.evidence["error"])
        result = create_resp.get("result") if isinstance(create_resp, dict) else None
        if not isinstance(result, dict):
            result = create_resp if isinstance(create_resp, dict) else {}
        ack_order_id = str(result.get("orderId") or result.get("order_id") or "")
        if ack_order_id:
            self.ledger.transition(
                entry_intent_id,
                "ACCEPTED",
                source="bybit_create_ack",
                exchange={"order_id": ack_order_id, "status": "Created"},
            )
        else:
            self.ledger.transition(entry_intent_id, "SUBMIT_UNKNOWN", source="bybit_create_ack_missing_id")

        entry_state, entry_order, entry_pos = self._wait_fill(
            symbol, entry_intent_id, order_link_id, ack_order_id, self.fill_timeout_sec
        )
        self.evidence["P1_ENTRY_RECONCILIATION_PASS"] = entry_state == "FILLED" and bool(entry_pos)
        if entry_state != "FILLED" or not entry_pos:
            self.evidence["error"] = f"entry_not_filled:{entry_state}"
            self.evidence["orphan_or_unresolved"] = True
            return self._finalize(hold_reason=self.evidence["error"])

        filled_qty = str(entry_order.get("cumExecQty") or entry_pos.get("size") or qty)
        entry_price = str(entry_order.get("avgPrice") or entry_pos.get("avgPrice") or "")
        pos_side = str(entry_pos.get("side") or side)
        self.evidence["requested_qty"] = qty
        self.evidence["filled_qty"] = filled_qty
        self.evidence["entry"] = entry_price
        self.evidence["orderId_prefix"] = _safe_prefix(entry_order.get("orderId") or ack_order_id)
        self.evidence["symbol"] = symbol
        self.evidence["side"] = side

        close_intent_id = f"p1cls_{uuid.uuid4().hex[:16]}"
        close_intent = OrderIntent(
            order_intent_id=close_intent_id,
            decision_id=decision_id,
            trade_id=trade_id,
            campaign_id=P1_CAMPAIGN_ID,
            symbol=symbol,
            side="Sell" if pos_side.lower() == "buy" else "Buy",
            requested_qty=_d(filled_qty),
            order_type="Market",
            reduce_only=True,
            parent_order_intent_id=entry_intent_id,
        )
        close_link_id = self.ledger.create_intent(close_intent)
        self.ledger.transition(entry_intent_id, "CLOSE_PENDING", source="p1_close_intent")
        self.ledger.transition(close_intent_id, "SUBMITTING", source="p1_close_pre_submit")
        try:
            self.create_order_calls += 1
            close_resp = self.client.close_reduce_only(
                symbol=symbol,
                side=pos_side,
                qty=str(filled_qty),
                order_link_id=close_link_id,
            )
        except Exception as exc:  # noqa: BLE001
            self.ledger.transition(
                close_intent_id,
                "SUBMIT_UNKNOWN",
                source="bybit_close_error",
                exchange={"reject_reason": type(exc).__name__},
            )
            self.evidence["error"] = f"close_submit_unknown:{type(exc).__name__}"
            self.evidence["fail_closed"] = True
            self.evidence["orphan_or_unresolved"] = True
            return self._finalize(hold_reason=self.evidence["error"])
        close_result = close_resp.get("result") if isinstance(close_resp, dict) else None
        if not isinstance(close_result, dict):
            close_result = close_resp if isinstance(close_resp, dict) else {}
        close_order_id = str(close_result.get("orderId") or close_result.get("order_id") or "")
        if close_order_id:
            self.ledger.transition(
                close_intent_id,
                "ACCEPTED",
                source="bybit_close_ack",
                exchange={"order_id": close_order_id, "status": "Created"},
            )
        close_state, close_order, close_pos = self._wait_fill(
            symbol, close_intent_id, close_link_id, close_order_id, self.close_timeout_sec, expect_flat=True
        )
        final_positions = list(self.client.list_positions(symbol) or [])
        flat = not final_positions
        self.evidence["P1_CLOSE_RECONCILIATION_PASS"] = close_state == "FILLED" and flat
        self.evidence["final_position_qty"] = "0" if flat else str((final_positions[0] or {}).get("size") or "")
        if not flat or close_state != "FILLED":
            self.evidence["error"] = "close_not_flat" if not flat else f"close_not_filled:{close_state}"
            self.evidence["fail_closed"] = True
            self.evidence["orphan_or_unresolved"] = True
            return self._finalize(hold_reason=self.evidence["error"])

        self.ledger.transition(entry_intent_id, "CLOSED", source="p1_position_flat")
        if close_state == "FILLED":
            try:
                self.ledger.transition(close_intent_id, "FILLED", source="bybit_close_fill", exchange=exchange_state(close_order)[1])
            except ValueError:
                pass
            try:
                self.ledger.transition(close_intent_id, "CLOSED", source="p1_close_complete")
            except ValueError:
                pass

        accounting = self._exchange_accounting(
            symbol=symbol,
            side=side,
            qty=filled_qty,
            entry_order=entry_order,
            close_order=close_order,
            wallet_before=preflight.get("wallet_before") or {},
            account=preflight.get("account") or {},
            entry_order_id=str(entry_order.get("orderId") or ack_order_id),
            close_order_id=str(close_order.get("orderId") or close_order_id),
        )
        self.ledger.record_accounting(
            entry_intent_id,
            actual_entry_price=accounting.get("actual_entry_price"),
            actual_exit_price=accounting.get("actual_exit_price"),
            fees=accounting.get("fees"),
            realized_demo_pnl=accounting.get("realized_demo_pnl") if accounting.get("exchange_realized") else None,
            wallet_delta=accounting.get("wallet_delta"),
            closed_at=accounting.get("closed_at"),
            pnl_provenance=accounting.get("pnl_provenance"),
            accounting={"exchange_realized": bool(accounting.get("exchange_realized"))},
        )
        self.evidence["exit"] = accounting.get("actual_exit_price")
        self.evidence["fees"] = accounting.get("fees")
        self.evidence["realized_demo_pnl"] = (
            accounting.get("realized_demo_pnl") if accounting.get("exchange_realized") else None
        )
        self.evidence["P1_EXCHANGE_REALIZED_PNL_PASS"] = bool(accounting.get("exchange_realized"))
        if not accounting.get("exchange_realized"):
            self.evidence["error"] = "realized_pnl_not_exchange_sourced"
            return self._finalize(hold_reason=self.evidence["error"])

        history = self.ledger.history(entry_intent_id)
        states = _history_states(history)
        lifecycle_ok = _has_lifecycle(states) and _accepted_or_new_present(states)
        final_intent = self.ledger.get_intent(entry_intent_id) or {}
        self.evidence["P1_DURABLE_LEDGER_LIFECYCLE_PASS"] = lifecycle_ok and final_intent.get("state") == "CLOSED"
        self.evidence["ledger_final_state"] = final_intent.get("state")
        self.evidence["ledger_states"] = states
        if not self.evidence["P1_DURABLE_LEDGER_LIFECYCLE_PASS"]:
            self.evidence["error"] = "ledger_lifecycle_incomplete"
            return self._finalize(hold_reason=self.evidence["error"])

        self.evidence["Demo_account_execution_source"] = "api-demo.bybit.com"
        return self._finalize(hold_reason=None)

    def _wait_fill(
        self,
        symbol: str,
        intent_id: str,
        order_link_id: str,
        order_id: str,
        timeout_sec: float,
        *,
        expect_flat: bool = False,
    ) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
        deadline = self.time_fn() + timeout_sec
        last_state = "SUBMITTING"
        last_order: dict[str, Any] = {}
        last_pos: dict[str, Any] | None = None
        while self.time_fn() <= deadline:
            order = self.client.find_order(symbol=symbol, order_id=order_id, order_link_id=order_link_id)
            if order:
                last_order = order
                last_state, exchange = exchange_state(order)
                try:
                    self.ledger.transition(intent_id, last_state, source="bybit_order_lookup", exchange=exchange)
                except ValueError:
                    pass
            positions = list(self.client.list_positions(symbol) or [])
            last_pos = positions[0] if positions else None
            if last_state == "FILLED":
                if expect_flat:
                    if last_pos is None:
                        return last_state, last_order, None
                elif last_pos is not None:
                    return last_state, last_order, last_pos
            if last_state in {"REJECTED", "CANCELLED"}:
                return last_state, last_order, last_pos
            self.sleep(POLL_INTERVAL_SEC)
        return last_state, last_order, last_pos

    def _exchange_accounting(
        self,
        *,
        symbol: str,
        side: str,
        qty: str,
        entry_order: dict[str, Any],
        close_order: dict[str, Any],
        wallet_before: dict[str, Any],
        account: dict[str, Any],
        entry_order_id: str,
        close_order_id: str,
    ) -> dict[str, Any]:
        executions = list(self.client.list_executions(symbol=symbol, limit=50) or [])
        closed_rows = list(self.client.list_closed_pnl(symbol=symbol, limit=50) or [])
        wallet_after = self.client.fetch_wallet_snapshot()
        entry_fills = [row for row in executions if str(row.get("orderId") or "") == str(entry_order_id)]
        close_fills = [row for row in executions if str(row.get("orderId") or "") == str(close_order_id)]
        fee_total = Decimal("0")
        for row in entry_fills + close_fills:
            fee_total += abs(_d(row.get("execFee")))
        close_pnl_row = _match_closed_pnl(
            closed_rows,
            close_order_id=close_order_id,
            entry_order_id=entry_order_id,
            close_link_id=str(close_order.get("orderLinkId") or ""),
        )
        closed_pnl = None if close_pnl_row is None else close_pnl_row.get("closedPnl")
        exit_price = (
            (close_fills[-1].get("execPrice") if close_fills else None)
            or close_order.get("avgPrice")
            or (close_pnl_row or {}).get("avgExitPrice")
        )
        entry_price = (
            (entry_fills[0].get("execPrice") if entry_fills else None)
            or entry_order.get("avgPrice")
            or (close_pnl_row or {}).get("avgEntryPrice")
        )
        provenance = classify_pnl_provenance(
            exchange_closed_pnl=closed_pnl,
            exchange_exec_fee=fee_total,
            has_exchange_fill=bool(entry_fills and close_fills and closed_pnl is not None),
        )
        exchange_realized = provenance.get("pnl_provenance") == "EXCHANGE_REALIZED_PNL" and closed_pnl is not None
        before = _d(wallet_before.get("wallet_balance") or wallet_before.get("coin_balance"))
        after = _d(wallet_after.get("wallet_balance") or wallet_after.get("coin_balance"))
        record = build_lifecycle_accounting_record(
            lifecycle={
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "position_zero": True,
                "bybit_orderId": entry_order_id,
                "bybit_executionId": (entry_fills[0].get("execId") if entry_fills else None),
            },
            account_identity=account,
            wallet_before=wallet_before,
            wallet_after=wallet_after,
            exchange_fill=entry_fills[0] if entry_fills else entry_order,
            exchange_close=close_pnl_row or {},
        )
        return {
            "actual_entry_price": _full(_d(entry_price)) if entry_price not in (None, "") else None,
            "actual_exit_price": _full(_d(exit_price)) if exit_price not in (None, "") else None,
            "fees": _full(fee_total),
            "realized_demo_pnl": _full(_d(closed_pnl)) if closed_pnl is not None else None,
            "wallet_delta": _full(after - before),
            "closed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pnl_provenance": provenance.get("pnl_provenance"),
            "exchange_realized": exchange_realized,
            "accounting_status": record.get("accounting_status"),
        }

    def _base_evidence(self) -> dict[str, Any]:
        return {
            "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
            "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
            "BYBIT_DEMO_SECRET_BOUNDARY_PASS": False,
            "BYBIT_DEMO_P1_LEDGER_CONNECTION_PASS": False,
            "P1_PREFLIGHT_PASS": False,
            "P1_ENTRY_RECONCILIATION_PASS": False,
            "P1_CLOSE_RECONCILIATION_PASS": False,
            "P1_EXCHANGE_REALIZED_PNL_PASS": False,
            "P1_DURABLE_LEDGER_LIFECYCLE_PASS": False,
            "PRE_ENTRY_KILL_SWITCH_PASS": False,
            "PRE_ENTRY_RECONCILIATION_PASS": False,
            "FRESH_OFFICIAL_EXECUTION_DATA_PASS": False,
            "NO_MOCK_EXECUTION_PRICE_PASS": False,
            "RISK_ENGINE_FINAL_AUTHORITY_PASS": False,
            "create_order_calls": 0,
            "recurring_loop": False,
            "service_disarmed": True,
        }

    def _disarm_process(self) -> dict[str, str]:
        for key, value in DISARMED_FLAGS.items():
            os.environ[key] = value
        return dict(DISARMED_FLAGS)

    def _finalize(self, *, hold_reason: str | None) -> dict[str, Any]:
        flags = self._disarm_process()
        writes = int(getattr(self.client, "write_call_count", self.create_order_calls) or 0)
        self.evidence["create_order_calls"] = self.create_order_calls
        self.evidence["exchange_write_call_count"] = writes
        self.evidence["recurring_loop"] = False
        self.evidence["service_disarmed"] = True
        self.evidence["process_flags"] = flags
        self.evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = "HOLD"
        all_pass = (
            hold_reason is None
            and self.evidence.get("P1_PREFLIGHT_PASS")
            and self.evidence.get("P1_ENTRY_RECONCILIATION_PASS")
            and self.evidence.get("P1_CLOSE_RECONCILIATION_PASS")
            and self.evidence.get("P1_EXCHANGE_REALIZED_PNL_PASS")
            and self.evidence.get("P1_DURABLE_LEDGER_LIFECYCLE_PASS")
            and self.evidence.get("BYBIT_DEMO_SECRET_BOUNDARY_PASS")
            and self.evidence.get("BYBIT_DEMO_P1_LEDGER_CONNECTION_PASS")
        )
        self.evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "PASS" if all_pass else "HOLD"
        if hold_reason and "error" not in self.evidence:
            self.evidence["error"] = hold_reason
        return sanitize_evidence(self.evidence)


def sanitize_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_secrets(payload)
    for key in SECRET_ENV_KEYS:
        redacted.pop(key, None)
        if "preflight" in redacted and isinstance(redacted["preflight"], dict):
            redacted["preflight"].pop(key, None)
    text = json.dumps(redacted, default=str)
    for key in SECRET_ENV_KEYS:
        value = os.environ.get(key) or ""
        if value:
            text = text.replace(value, "[REDACTED]")
    return json.loads(text)


def _open_pool():
    from backend.nexus_persistence_pg.pool import PostgresPool

    url = _postgres_url()
    if not url:
        raise RuntimeError("postgres_url_missing")
    pool = PostgresPool(url)
    pool.open()
    return pool


def _apply_pending(pool: Any) -> dict[str, Any]:
    from backend.nexus_persistence_pg.migrate import MigrationRunner

    return MigrationRunner().apply_pending(pool)


def run_p1_qualification(
    *,
    client: Any | None = None,
    ledger: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now_ms: Callable[[], int] = _now_ms,
    apply_pending_schema: Callable[[], dict[str, Any]] | None = None,
    time_fn: Callable[[], float] = time.time,
    fill_timeout_sec: float = FILL_TIMEOUT_SEC,
    close_timeout_sec: float = CLOSE_TIMEOUT_SEC,
) -> dict[str, Any]:
    pool = None
    owns_pool = False
    try:
        if client is None:
            if not _authorized():
                runner = P1QualificationRunner(
                    client=_NullClient(),
                    ledger=_NullLedger(),
                    sleep=sleep,
                    now_ms=now_ms,
                    time_fn=time_fn,
                    fill_timeout_sec=fill_timeout_sec,
                    close_timeout_sec=close_timeout_sec,
                )
                return runner.run()
            client = DemoWriteClient()
        if ledger is None:
            pool = _open_pool()
            owns_pool = True
            ledger = DurableOrderLedger(pool)
            if apply_pending_schema is None:
                apply_pending_schema = lambda: _apply_pending(pool)
        runner = P1QualificationRunner(
            client=client,
            ledger=ledger,
            sleep=sleep,
            now_ms=now_ms,
            apply_pending_schema=apply_pending_schema,
            time_fn=time_fn,
            fill_timeout_sec=fill_timeout_sec,
            close_timeout_sec=close_timeout_sec,
        )
        return runner.run()
    finally:
        if owns_pool and pool is not None:
            pool.close()


class _NullClient:
    base_url = DEMO_REST_BASE_URL
    api_key = ""
    api_secret = ""
    write_call_count = 0

    def create_market_order(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("create_market_order_without_authorization")

    def close_reduce_only(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("close_reduce_only_without_authorization")


class _NullLedger:
    def required_migrations_present(self) -> dict[str, Any]:
        return {"ok": False, "missing": ["unauthorized"]}

    def probe_write_read(self) -> dict[str, Any]:
        return {"ok": False}

    def unfinished(self) -> list[dict[str, Any]]:
        return []

    def create_intent(self, intent: OrderIntent) -> str:
        raise AssertionError("create_intent_without_authorization")


def _write_artifacts(evidence: dict[str, Any]) -> None:
    root = Path("artifacts") / "bybit_demo_p1"
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / "p1_qualification_evidence.json").write_text(
            json.dumps(evidence, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        return
    remote_path = os.environ.get("P1_EVIDENCE_PATH") or ""
    if remote_path:
        try:
            destination = Path(remote_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass
    report_path = os.environ.get("NEXUS_FINAL_ACCELERATION_REPORT") or ""
    if not report_path:
        candidate = Path(r"D:\NEXUS_RUNTIME\NEXUS_FINAL_ACCELERATION_REPORT.json")
        if candidate.exists():
            report_path = str(candidate)
    if not report_path:
        return
    path = Path(report_path)
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(current, dict):
            current = {}
        current["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = evidence.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS")
        current["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = "HOLD"
        current["bybit_demo_p1_qualification"] = evidence
        path.write_text(json.dumps(current, indent=2, default=str), encoding="utf-8")
    except OSError:
        return


def main() -> int:
    evidence = run_p1_qualification()
    _write_artifacts(evidence)
    print(json.dumps(evidence, default=str))
    return 0 if evidence.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
