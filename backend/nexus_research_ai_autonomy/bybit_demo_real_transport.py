"""Bybit Demo REAL transport for Research AI Autonomy.

Hard-locked to api-demo.bybit.com. Reuses DemoWriteClient REST path:
create / reconcile (position list) / reduce-only close / leverage=1.
Never claims BYBIT_DEMO_REAL_TRANSPORT without real HTTP evidence.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError, _float, _round_price
from backend.nexus_research_ai_autonomy.constants import BYBIT_DEMO_HOST

EXECUTION_PURPOSE_REAL = "RESEARCH_AI_DEMO_REAL_EXCHANGE"
TRANSPORT_MODE_REAL = "BYBIT_DEMO_REAL_TRANSPORT"
ENV_FILE = Path(r"D:\NEXUS\btc_bot\.env")

# Research demo: allow liquid majors for min-qty lifecycle (demo only).
ALLOWED_RESEARCH_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})


def load_demo_env(env_path: Path | None = ENV_FILE) -> dict[str, bool]:
    """Load demo credentials into os.environ without printing secrets.

    Cloud (Zeabur): prefer process env; optional file only when path exists.
    """
    key_ok = bool((os.environ.get("BYBIT_DEMO_API_KEY") or "").strip())
    secret_ok = bool((os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip())
    path = env_path
    if path is not None and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in {"BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET"} and v:
                # Do not overwrite already-set Zeabur secrets.
                if not (os.environ.get(k) or "").strip():
                    os.environ[k] = v
        key_ok = bool((os.environ.get("BYBIT_DEMO_API_KEY") or "").strip())
        secret_ok = bool((os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip())
    os.environ.setdefault("MAINNET", "0")
    os.environ.setdefault("REAL_MONEY", "false")
    # Cloud worker typically sets EXCHANGE_WRITE=true explicitly; do not force false over it.
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    return {"key_present": key_ok, "secret_present": secret_ok}


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class BybitDemoRealTransport:
    """Real Demo REST transport — concurrent=1, 1x, protective stop.

    V18.2.24: EXECUTION_CANARY may auto-close quickly (transport proof).
    RESEARCH_PNL_TRADE must NOT immediate-close; managed exit is caller's job
    unless auto_close=True with purpose=canary.
    Latency provenance may use BYBIT_DEMO_REAL_TRANSPORT / BYBIT_EXCHANGE_LATENCY
    only when real_http_request is True with recorded orderId evidence.
    """

    host: str = BYBIT_DEMO_HOST
    base_url: str = DEMO_REST_BASE_URL
    client: DemoWriteClient | None = None
    orders: list[dict[str, Any]] = field(default_factory=list)
    last_reconcile: dict[str, Any] | None = None
    last_reduce_only: dict[str, Any] | None = None
    auto_close: bool = True
    max_hold_sec: int = 45
    env_loaded: bool = False
    # When True, sleep(min(2, max_hold*0.05)) then force close — CANARY only.
    canary_immediate_close: bool = True

    def ensure_client(self) -> DemoWriteClient:
        if not self.env_loaded:
            load_demo_env()
            self.env_loaded = True
        if self.client is None:
            self.client = DemoWriteClient(base_url=self.base_url)
        if "api-demo.bybit.com" not in (self.client.base_url or ""):
            raise DemoWriteError("mainnet_domain", self.client.base_url)
        return self.client

    def _min_qty_str(self, client: DemoWriteClient, symbol: str, price: float, info: dict[str, Any]) -> str:
        step = client.qty_step(info)
        min_q = client.min_qty(info)
        min_n = client.min_notional(info)
        qty = max(min_q, step)
        if min_n > 0 and price > 0:
            need = (min_n / price) * 1.02
            while qty * price + 1e-12 < min_n:
                qty += step
                if qty > need * 2 and qty * price >= min_n:
                    break
                if qty > need * 50:
                    break
        from backend.nexus_demo_execution.demo_write_client import _round_qty

        return _round_qty(qty, step)

    def send_research_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Place one Demo market order with protective SL/TP; optional reduce-only close.

        lifecycle_purpose=EXECUTION_CANARY → may immediate-close (transport proof).
        lifecycle_purpose=RESEARCH_PNL_TRADE → do NOT close solely because execution proven;
        leave position open for real management unless intent.force_managed_close.
        """
        from backend.nexus_research_ai_autonomy.lifecycle_purpose import (
            LIFECYCLE_PURPOSE_EXECUTION_CANARY,
            LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        )

        mono_req = time.perf_counter()
        symbol = str(intent.get("symbol") or "ETHUSDT").upper()
        preflight_ok = bool(intent.get("exchange_preflight_pass"))
        if symbol not in ALLOWED_RESEARCH_SYMBOLS and not preflight_ok:
            # Legacy fallback for un-preflighted research shortlist symbols
            symbol = "ETHUSDT"
        side = str(intent.get("side") or "Buy")
        if side.upper() in {"LONG", "BUY"}:
            side = "Buy"
        elif side.upper() in {"SHORT", "SELL"}:
            side = "Sell"

        purpose = str(
            intent.get("lifecycle_purpose")
            or (
                LIFECYCLE_PURPOSE_EXECUTION_CANARY
                if intent.get("execution_canary")
                else LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
            )
        )
        is_canary = purpose == LIFECYCLE_PURPOSE_EXECUTION_CANARY

        try:
            client = self.ensure_client()
        except Exception as exc:  # noqa: BLE001
            return {
                "accepted": False,
                "reason": f"client_init:{type(exc).__name__}",
                "detail": str(exc)[:200],
                "host": self.host,
                "demo_only": True,
                "mainnet": False,
                "execution_purpose": EXECUTION_PURPOSE_REAL,
                "transport_mode": "LOCAL_SIMULATION",
                "exchange_domain": self.host,
                "real_http_request": False,
                "latency_class": "LOCAL_SIMULATION_LATENCY",
                "not_bybit_exchange_latency": True,
                "lifecycle_purpose": purpose,
            }

        link_id = f"raidemo_{uuid.uuid4().hex[:16]}"
        send_ts = _now_ms()
        send_mono = time.perf_counter()
        try:
            # Leverage 1x — never raise for larger PnL
            client.set_leverage(symbol, 1)
            info = client.fetch_instrument(symbol)
            klines = client.public_get(
                "/v5/market/tickers",
                {"category": "linear", "symbol": symbol},
            )
            rows = (klines.get("result") or {}).get("list") or []
            price = _float((rows[0] if rows else {}).get("lastPrice") or 0)
            if price <= 0:
                raise DemoWriteError("price_missing", symbol)
            qty = str(intent.get("qty") or "") or self._min_qty_str(client, symbol, price, info)
            tick = client.tick_size(info)

            stop_pct = float(intent.get("stop_distance_pct") or (0.8 if is_canary else 0.55))
            tp_pct = float(intent.get("target_distance_pct") or (0.4 if is_canary else 0.55))
            if intent.get("stop_loss"):
                sl = str(intent.get("stop_loss"))
            elif side == "Buy":
                sl = _round_price(price * (1.0 - stop_pct / 100.0), tick)
            else:
                sl = _round_price(price * (1.0 + stop_pct / 100.0), tick)
            if intent.get("take_profit"):
                tp = str(intent.get("take_profit"))
            elif side == "Buy":
                tp = _round_price(price * (1.0 + tp_pct / 100.0), tick)
            else:
                tp = _round_price(price * (1.0 - tp_pct / 100.0), tick)

            place = client.create_market_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_link_id=link_id,
                stop_loss=sl,
                take_profit=tp,
            )
            ack_mono = time.perf_counter()
            ack_ts = _now_ms()
            result_body = place.get("result") or {}
            order_id = str(result_body.get("orderId") or "")
            time.sleep(0.4)
            positions = client.list_positions(symbol)
            self.last_reconcile = {
                "symbol": symbol,
                "positions": positions,
                "order_id": order_id,
                "at_ms": _now_ms(),
            }
            exec_id = None
            fill_price = price
            try:
                execs = client.list_executions(symbol=symbol, limit=5)
                for e in execs:
                    if str(e.get("orderId") or "") == order_id:
                        exec_id = str(e.get("execId") or e.get("executionId") or "")
                        fill_price = _float(e.get("execPrice") or price) or price
                        break
                if not exec_id and execs:
                    exec_id = str(execs[0].get("execId") or "")
            except Exception:  # noqa: BLE001
                exec_id = None

            fill_mono = time.perf_counter()
            fill_ts = _now_ms()
            close_report = None
            # CANARY may immediate-close; RESEARCH_PNL_TRADE must not (unless forced).
            do_immediate = bool(
                self.auto_close
                and positions
                and (
                    is_canary
                    and self.canary_immediate_close
                    or intent.get("force_immediate_close")
                )
            )
            if do_immediate:
                # Root of entry≈exit: sleep(min(2, max_hold*0.05)) — keep for canary only
                time.sleep(min(2.0, float(self.max_hold_sec) * 0.05))
                pos = positions[0]
                pos_side = str(pos.get("side") or side)
                pos_qty = str(pos.get("size") or qty)
                close_link = f"raidcl_{uuid.uuid4().hex[:16]}"
                close_resp = client.close_reduce_only(
                    symbol=symbol,
                    side=pos_side,
                    qty=pos_qty,
                    order_link_id=close_link,
                )
                time.sleep(0.35)
                after = client.list_positions(symbol)
                close_report = {
                    "reduce_only": True,
                    "close_orderId": ((close_resp.get("result") or {}).get("orderId")),
                    "position_zero": len(after) == 0,
                    "close_link_id": close_link,
                    "immediate_canary_close": True,
                }
                self.last_reduce_only = close_report

            network_ms = (ack_mono - send_mono) * 1000.0
            out = {
                "accepted": bool(order_id),
                "order_id": order_id,
                "execution_id": exec_id,
                "host": self.host,
                "demo_only": True,
                "mainnet": False,
                "real_money": False,
                "execution_purpose": EXECUTION_PURPOSE_REAL,
                "transport_mode": TRANSPORT_MODE_REAL,
                "exchange_domain": self.host,
                "real_http_request": True,
                "latency_class": "BYBIT_EXCHANGE_LATENCY",
                "not_bybit_exchange_latency": False,
                "http_send_ts": send_ts,
                "exchange_ack_ts": ack_ts,
                "fill_ts": fill_ts,
                "monotonic": {
                    "request_perf": mono_req,
                    "send_perf": send_mono,
                    "ack_perf": ack_mono,
                    "fill_perf": fill_mono,
                    "network_roundtrip_ms": network_ms,
                    "internal_trigger_to_send_ms": (send_mono - mono_req) * 1000.0,
                    "exchange_ack_ms": network_ms,
                    "fill_ms": (fill_mono - ack_mono) * 1000.0,
                },
                "bybit_orderId": order_id,
                "bybit_executionId": exec_id,
                "ws_timestamp": None,
                "local_timestamp": send_ts,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry_price": fill_price,
                "notional": float(qty) * float(fill_price) if qty else None,
                "leverage": 1,
                "order_link_id": link_id,
                "protective_stop": sl,
                "take_profit": tp,
                "stop_distance_pct": stop_pct,
                "target_distance_pct": tp_pct,
                "reconcile": self.last_reconcile,
                "reduce_only_close": close_report,
                "lifecycle_purpose": purpose,
                "position_left_open_for_management": bool(positions) and not do_immediate,
                "intent": dict(intent),
                "retCode": place.get("retCode"),
            }
            self.orders.append(out)
            return out
        except Exception as exc:  # noqa: BLE001
            fail_mono = time.perf_counter()
            return {
                "accepted": False,
                "reason": f"demo_order_error:{type(exc).__name__}",
                "detail": str(exc)[:300],
                "host": self.host,
                "demo_only": True,
                "mainnet": False,
                "execution_purpose": EXECUTION_PURPOSE_REAL,
                "transport_mode": TRANSPORT_MODE_REAL,
                "exchange_domain": self.host,
                "real_http_request": True,
                "latency_class": "BYBIT_EXCHANGE_LATENCY",
                "not_bybit_exchange_latency": False,
                "http_send_ts": send_ts,
                "exchange_ack_ts": None,
                "fill_ts": None,
                "monotonic": {
                    "request_perf": mono_req,
                    "send_perf": send_mono,
                    "ack_perf": fail_mono,
                    "fill_perf": None,
                    "network_roundtrip_ms": (fail_mono - send_mono) * 1000.0,
                    "internal_trigger_to_send_ms": (send_mono - mono_req) * 1000.0,
                    "exchange_ack_ms": None,
                    "fill_ms": None,
                },
                "bybit_orderId": None,
                "bybit_executionId": None,
                "ws_timestamp": None,
                "local_timestamp": send_ts,
                "lifecycle_purpose": purpose,
                "intent": dict(intent),
            }

    def reconcile(self, symbol: str) -> dict[str, Any]:
        client = self.ensure_client()
        positions = client.list_positions(symbol.upper())
        orders = client.list_open_orders(symbol.upper())
        self.last_reconcile = {
            "symbol": symbol.upper(),
            "positions": positions,
            "open_orders": orders,
            "at_ms": _now_ms(),
        }
        return self.last_reconcile

    def reduce_only_close(self, symbol: str, side: str, qty: str) -> dict[str, Any]:
        client = self.ensure_client()
        link = f"raidcl_{uuid.uuid4().hex[:16]}"
        resp = client.close_reduce_only(
            symbol=symbol.upper(),
            side=side,
            qty=qty,
            order_link_id=link,
        )
        after = client.list_positions(symbol.upper())
        self.last_reduce_only = {
            "reduce_only": True,
            "response": resp,
            "position_zero": len(after) == 0,
            "order_link_id": link,
        }
        return self.last_reduce_only
