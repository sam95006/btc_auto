import asyncio
import threading
import time

try:
    import websockets
except Exception:
    websockets = None

from backend.trading.binance_sync_models import FuturesAccountSnapshot, SpotAccountSnapshot, SyncStatus
from backend.trading.binance_spot_user_stream_manager import BinanceSpotUserStreamManager


class BinanceAccountSyncService:
    def __init__(self, spot_client=None, futures_client=None):
        self.spot_client = spot_client
        self.futures_client = futures_client
        self.spot_status = SyncStatus()
        self.futures_status = SyncStatus()
        self.spot_stream_manager = BinanceSpotUserStreamManager(spot_client) if spot_client else None
        self._stop = threading.Event()
        self._thread = None
        self._event_cache = {"spot": [], "futures": []}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        if websockets is None:
            self.spot_status.websocket_status = "degraded"
            self.futures_status.websocket_status = "degraded"
            return
        self._thread = threading.Thread(target=self._run_ws_loop, daemon=True, name="binance-account-sync")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run_ws_loop(self):
        asyncio.run(self._runner())

    async def _runner(self):
        while not self._stop.is_set():
            await asyncio.gather(
                self._spot_stream_loop(),
                self._futures_stream_loop(),
                return_exceptions=True,
            )
            await asyncio.sleep(2)

    async def _spot_stream_loop(self):
        if not self.spot_stream_manager:
            self.spot_status.websocket_status = "disconnected"
            return
        if not (self.spot_client and self.spot_client.is_configured()):
            self.spot_status.websocket_status = "disconnected"
            return
        await self.spot_stream_manager.stream_forever(self._stop)

    async def _futures_stream_loop(self):
        if not (self.futures_client and self.futures_client.is_configured()):
            self.futures_status.websocket_status = "disconnected"
            return
        try:
            listen_key = self.futures_client.create_listen_key()
            self.futures_status.websocket_status = "connected"
            url = self.futures_client.build_user_stream_url(listen_key)
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                last_keepalive = time.time()
                while not self._stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=55)
                    self._event_cache["futures"].append(raw)
                    self._event_cache["futures"] = self._event_cache["futures"][-200:]
                    self.futures_status.connected = True
                    self.futures_status.last_sync_time = int(time.time() * 1000)
                    if time.time() - last_keepalive >= 25 * 60:
                        self.futures_client.keepalive_listen_key(listen_key)
                        last_keepalive = time.time()
        except Exception as exc:
            self.futures_status.websocket_status = "degraded"
            self.futures_status.errors = [str(exc)]

    def build_spot_snapshot(self, balances, open_orders, trades, total_equity, last_sync_time, sync_error=""):
        snapshot = SpotAccountSnapshot(
            balances=balances,
            free={asset: item.get("free", 0.0) for asset, item in balances.items()},
            locked={asset: item.get("locked", 0.0) for asset, item in balances.items()},
            total_equity_usdt=round(float(total_equity or 0.0), 4),
            open_orders=list(open_orders or []),
            trade_history=list(trades or []),
            last_sync_time=int(last_sync_time or 0),
            sync_status="connected" if not sync_error else "degraded",
            sync_error=sync_error or "",
        )
        self.spot_status.connected = not bool(sync_error)
        self.spot_status.rest_snapshot_status = "ok" if not sync_error else "degraded"
        self.spot_status.last_sync_time = snapshot.last_sync_time
        if self.spot_stream_manager:
            self.spot_stream_manager.reconcile_rest_snapshot()
            health = self.spot_stream_manager.health_snapshot()
            self.spot_status.websocket_status = health["status"]
            if health["errors"] and not sync_error:
                self.spot_status.errors = list(health["errors"][-3:])
            self._event_cache["spot"] = self.spot_stream_manager.recent_events(limit=200)
        return snapshot

    def build_futures_snapshot(self, account, positions, open_orders, fills, funding_rates, last_sync_time, sync_error=""):
        snapshot = FuturesAccountSnapshot(
            total_wallet_balance=round(float(account.get("totalWalletBalance", 0.0) or 0.0), 4),
            available_balance=round(float(account.get("availableBalance", 0.0) or 0.0), 4),
            total_unrealized_profit=round(float(account.get("totalUnrealizedProfit", 0.0) or 0.0), 4),
            total_margin_balance=round(float(account.get("totalMarginBalance", 0.0) or 0.0), 4),
            positions=list(positions or []),
            open_orders=list(open_orders or []),
            order_updates=list(self._event_cache["futures"][-50:]),
            fills=list(fills or []),
            funding_rates=list(funding_rates or []),
            last_sync_time=int(last_sync_time or 0),
            sync_status="connected" if not sync_error else "degraded",
            sync_error=sync_error or "",
        )
        self.futures_status.connected = not bool(sync_error)
        self.futures_status.rest_snapshot_status = "ok" if not sync_error else "degraded"
        self.futures_status.last_sync_time = snapshot.last_sync_time
        return snapshot
