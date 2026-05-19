import threading
import time


class BinanceRateLimitError(RuntimeError):
    pass


class BinanceRateLimitGuard:
    def __init__(self, min_retry_delay=1.0, max_retry_delay=30.0):
        self._lock = threading.RLock()
        self.min_retry_delay = float(min_retry_delay)
        self.max_retry_delay = float(max_retry_delay)
        self.used_weight = None
        self.order_count = None
        self.last_status = "idle"
        self.last_error = ""
        self.ban_active = False
        self.backoff_until = 0.0
        self.last_headers = {}

    def before_request(self):
        with self._lock:
            if self.ban_active:
                raise BinanceRateLimitError("binance_rate_limit_ban_active")
            if self.backoff_until and time.time() < self.backoff_until:
                raise BinanceRateLimitError("binance_rate_limit_backoff_active")

    def after_response(self, status_code, headers=None):
        headers = headers or {}
        with self._lock:
            self.last_headers = dict(headers)
            used_weight = headers.get("x-mbx-used-weight-1m") or headers.get("X-MBX-USED-WEIGHT-1M")
            order_count = headers.get("x-mbx-order-count-10s") or headers.get("X-MBX-ORDER-COUNT-10S")
            self.used_weight = int(used_weight) if used_weight and str(used_weight).isdigit() else self.used_weight
            self.order_count = int(order_count) if order_count and str(order_count).isdigit() else self.order_count
            if status_code == 429:
                self.last_status = "backoff"
                self.backoff_until = time.time() + self.min_retry_delay
            elif status_code == 418:
                self.last_status = "banned"
                self.ban_active = True
                self.last_error = "http_418_ip_ban"
            else:
                self.last_status = "ok"
                self.backoff_until = 0.0

    def register_retry(self, attempt):
        with self._lock:
            delay = min(self.max_retry_delay, self.min_retry_delay * max(1, attempt))
            self.backoff_until = time.time() + delay
            return delay

    def snapshot(self):
        with self._lock:
            return {
                "used_weight": self.used_weight,
                "order_count": self.order_count,
                "last_status": self.last_status,
                "last_error": self.last_error,
                "ban_active": self.ban_active,
                "backoff_until": self.backoff_until,
            }
