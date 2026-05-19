import asyncio
import json
import threading
import time

try:
    import websockets
except Exception:
    websockets = None


class SpotListenKeyExpiredError(RuntimeError):
    pass


class SpotStreamMaintenanceError(RuntimeError):
    pass


class BinanceSpotUserStreamManager:
    def __init__(self, spot_client, reconnect_base_delay=1.0, reconnect_max_delay=30.0):
        self.spot_client = spot_client
        self.reconnect_base_delay = float(reconnect_base_delay)
        self.reconnect_max_delay = float(reconnect_max_delay)
        self._lock = threading.RLock()
        self._event_cache = []
        self._event_counts = {
            "executionReport": 0,
            "outboundAccountPosition": 0,
            "balanceUpdate": 0,
        }
        self._listen_key = ""
        self._listen_key_created_at = 0.0
        self._last_keepalive = 0.0
        self._last_reconcile = 0.0
        self._reconnect_attempt = 0
        self._status = "disconnected"
        self._connected = False
        self._errors = []
        self._last_sync_time = 0
        self._last_event_time = 0
        self._last_connect_time = 0
        self._status_detail = ""
        self._truth_mode = "stream"
        self._rest_only_until = 0.0

    def health_snapshot(self):
        with self._lock:
            return {
                "status": self._status,
                "status_detail": self._status_detail,
                "connected": self._connected,
                "truth_mode": self._truth_mode,
                "last_sync_time": self._last_sync_time,
                "listen_key_active": bool(self._listen_key),
                "reconnect_attempt": self._reconnect_attempt,
                "last_connect_time": int(self._last_connect_time * 1000) if self._last_connect_time else 0,
                "last_event_time": int(self._last_event_time * 1000) if self._last_event_time else 0,
                "last_keepalive_time": int(self._last_keepalive * 1000) if self._last_keepalive else 0,
                "last_rest_reconcile_time": int(self._last_reconcile * 1000) if self._last_reconcile else 0,
                "event_counts": dict(self._event_counts),
                "errors": list(self._errors[-5:]),
            }

    async def stream_forever(self, stop_event):
        if websockets is None or not (self.spot_client and self.spot_client.is_configured()):
            self._set_status(
                "degraded" if self.spot_client and self.spot_client.is_configured() else "disconnected",
                detail="websockets_unavailable" if self.spot_client and self.spot_client.is_configured() else "spot_not_configured",
                truth_mode="rest_only" if self.spot_client and self.spot_client.is_configured() else "stream",
            )
            return

        while not stop_event.is_set():
            with self._lock:
                rest_only_for_now = self._rest_only_until and time.time() < self._rest_only_until
            if rest_only_for_now:
                self._set_status("degraded", connected=False, detail="rest_only_due_to_spot_stream_unavailable", truth_mode="rest_only")
                await asyncio.sleep(max(self.reconnect_max_delay, 30.0))
                continue
            try:
                await self._connect_and_consume(stop_event)
                self._reconnect_attempt = 0
                if not stop_event.is_set():
                    self._set_status("reconnecting", connected=False, detail="stream_cycle_restarting", truth_mode="stream")
            except SpotStreamMaintenanceError as exc:
                self._record_error(exc, status="degraded")
                self._reconnect_attempt += 1
                await asyncio.sleep(max(self.reconnect_max_delay, 30.0))
            except Exception as exc:
                self._record_error(exc)
                self._reconnect_attempt += 1
                self._set_status("reconnecting", detail="stream_reconnect_backoff", truth_mode="stream")
                await asyncio.sleep(self._backoff_seconds())
        self._set_status("disconnected", connected=False, detail="stop_event", truth_mode="stream")

    def reconcile_rest_snapshot(self):
        with self._lock:
            self._last_reconcile = time.time()

    def recent_events(self, limit=100):
        with self._lock:
            return list(self._event_cache[-limit:])

    async def _connect_and_consume(self, stop_event):
        listen_key = self._ensure_listen_key()
        url = self.spot_client.build_user_stream_url(listen_key)
        self._set_status("reconnecting", connected=False, detail="opening_user_stream", truth_mode="stream")
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            with self._lock:
                self._last_connect_time = time.time()
                self._connected = True
                self._status = "connected"
                self._status_detail = "stream_connected"
                self._truth_mode = "stream"
                self._rest_only_until = 0.0
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=55)
                except asyncio.TimeoutError:
                    self._keepalive_if_needed()
                    continue
                self._inspect_stream_error(raw)
                self._record_event(raw)
                self._keepalive_if_needed()

    def _ensure_listen_key(self, force_new=False):
        with self._lock:
            if self._listen_key and not force_new:
                return self._listen_key
        try:
            listen_key = self.spot_client.create_listen_key()
        except Exception as exc:
            if self._is_listen_key_expired_error(exc):
                self._activate_rest_only_mode(str(exc))
                raise SpotStreamMaintenanceError(str(exc)) from exc
            raise
        with self._lock:
            self._listen_key = listen_key
            self._listen_key_created_at = time.time()
            self._last_keepalive = time.time()
        return listen_key

    def _keepalive_if_needed(self):
        with self._lock:
            listen_key = self._listen_key
            due = not self._last_keepalive or (time.time() - self._last_keepalive) >= (25 * 60)
        if listen_key and due:
            try:
                self.spot_client.keepalive_listen_key(listen_key)
            except Exception as exc:
                if self._is_listen_key_expired_error(exc):
                    self._invalidate_listen_key(str(exc))
                    self._activate_rest_only_mode(str(exc))
                    raise SpotStreamMaintenanceError(str(exc)) from exc
                raise
            else:
                with self._lock:
                    self._last_keepalive = time.time()

    def _inspect_stream_error(self, raw):
        try:
            parsed = json.loads(raw)
        except Exception:
            return
        code = parsed.get("code")
        message = str(parsed.get("msg") or parsed.get("message") or "")
        if code in (410, -1125) or "listen key" in message.lower():
            self._invalidate_listen_key(message or f"stream_error_{code}")
            raise SpotStreamMaintenanceError(message or f"spot_stream_error_{code}")

    def _invalidate_listen_key(self, reason=""):
        with self._lock:
            stale_listen_key = self._listen_key
            self._listen_key = ""
            self._listen_key_created_at = 0.0
            self._connected = False
            self._status = "reconnecting"
            self._status_detail = "listen_key_invalidated"
        if stale_listen_key:
            try:
                self.spot_client.close_listen_key(stale_listen_key)
            except Exception as exc:
                self._record_nonfatal_error(exc)
        if reason:
            self._record_nonfatal_error(reason)

    def _record_event(self, raw):
        event_type = "unknown"
        parsed = {"raw": raw}
        try:
            parsed = json.loads(raw)
            event_type = str(parsed.get("e") or "unknown")
        except Exception:
            pass
        with self._lock:
            self._event_cache.append(parsed)
            self._event_cache = self._event_cache[-200:]
            if event_type in self._event_counts:
                self._event_counts[event_type] += 1
            now = time.time()
            self._last_sync_time = int(now * 1000)
            self._last_event_time = now
            self._connected = True
            self._status = "connected"
            self._status_detail = f"event:{event_type}"
            self._truth_mode = "stream"
            self._rest_only_until = 0.0

    def _record_error(self, exc, status="degraded"):
        with self._lock:
            self._connected = False
            self._status = status
            self._status_detail = str(exc)
            self._errors.append(str(exc))
            self._errors = self._errors[-20:]

    def _record_nonfatal_error(self, exc):
        with self._lock:
            self._errors.append(str(exc))
            self._errors = self._errors[-20:]

    def _set_status(self, status, connected=None, detail=None, truth_mode=None):
        with self._lock:
            self._status = status
            if connected is not None:
                self._connected = connected
            if detail is not None:
                self._status_detail = str(detail)
            if truth_mode is not None:
                self._truth_mode = truth_mode

    def _activate_rest_only_mode(self, reason):
        with self._lock:
            self._connected = False
            self._status = "degraded"
            self._status_detail = f"rest_only:{reason}"
            self._truth_mode = "rest_only"
            self._rest_only_until = time.time() + max(self.reconnect_max_delay, 30.0)
            self._errors.append(str(reason))
            self._errors = self._errors[-20:]

    def _backoff_seconds(self):
        delay = self.reconnect_base_delay * (2 ** max(0, self._reconnect_attempt - 1))
        return min(self.reconnect_max_delay, delay)

    @staticmethod
    def _is_listen_key_expired_error(exc):
        text = str(exc).lower()
        return "410" in text or "gone" in text or "listenkey" in text or "listen key" in text or "-1125" in text
