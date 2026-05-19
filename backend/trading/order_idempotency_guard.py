import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path


class DuplicateOrderError(RuntimeError):
    pass


class OrderIdempotencyGuard:
    def __init__(self, db_path=None, window_seconds=30):
        self.db_path = db_path or os.getenv("NEXUS_RUNTIME_DB", "trading.db")
        self.window_seconds = int(window_seconds or 30)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._init_db()

    def _init_db(self):
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_order_idempotency (
                    fingerprint TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    order_meta_json TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def build_fingerprint(self, fleet, symbol, side, strategy_signal_hash, timestamp=None):
        ts = float(timestamp or time.time())
        window_bucket = int(ts // self.window_seconds)
        payload = {
            "fleet": str(fleet or "").upper(),
            "symbol": str(symbol or "").upper(),
            "side": str(side or "").upper(),
            "timestamp_window": window_bucket,
            "strategy_signal_hash": str(strategy_signal_hash or ""),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return digest, payload

    def claim(self, fleet, symbol, side, strategy_signal_hash, timestamp=None, metadata=None):
        now = float(timestamp or time.time())
        fingerprint, payload = self.build_fingerprint(fleet, symbol, side, strategy_signal_hash, timestamp=now)
        expiry = now + self.window_seconds
        meta = dict(metadata or {})
        meta.update(payload)
        self.cleanup_expired(now=now)
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT fingerprint FROM nexus_order_idempotency WHERE fingerprint=?",
                (fingerprint,),
            )
            if cursor.fetchone():
                return False, fingerprint
            cursor.execute(
                """
                INSERT INTO nexus_order_idempotency (fingerprint, created_at, expires_at, order_meta_json)
                VALUES (?, ?, ?, ?)
                """,
                (fingerprint, now, expiry, json.dumps(meta, ensure_ascii=False, sort_keys=True)),
            )
            self._conn.commit()
            return True, fingerprint

    def cleanup_expired(self, now=None):
        now = float(now or time.time())
        with self._lock:
            self._conn.execute(
                "DELETE FROM nexus_order_idempotency WHERE expires_at <= ?",
                (now,),
            )
            self._conn.commit()

    def recent_fingerprints(self, limit=50):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT fingerprint, created_at, expires_at, order_meta_json
                FROM nexus_order_idempotency
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["order_meta"] = json.loads(item.pop("order_meta_json"))
                except Exception:
                    item["order_meta"] = {}
                items.append(item)
            return items
