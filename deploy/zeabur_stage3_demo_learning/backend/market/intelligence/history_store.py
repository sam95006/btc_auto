"""Bounded Market Intelligence history persistence adapter (Phase 4 Track B).

Detects writable NEXUS_DATA_DIR; otherwise honest memory-only mode.
Never stores secrets, wallet, orders, or positions.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_TTL_MS = 6 * 60 * 60 * 1000  # 6h research retention
SAMPLE_CAPACITY_PER_SYMBOL = 180  # ~1h at ~20s or denser WS throttle
MAX_SYMBOLS = 120
JSONL_ROTATE_LINES = 50_000

_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "apiSecret",
        "api_secret",
        "secret",
        "private_key",
        "wallet",
        "orderId",
        "order_id",
        "position",
        "positions",
        "leverage",
        "password",
        "token",
        "authorization",
    }
)


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower().replace("-", "_")
            if k in _FORBIDDEN_KEYS or lk in {x.lower() for x in _FORBIDDEN_KEYS}:
                continue
            if "secret" in lk or "apikey" in lk or "private" in lk and "api" in lk:
                continue
            out[k] = _sanitize(v)
        return out
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj[:500]]
    return obj


def _writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".nexus_mi_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:  # noqa: BLE001
        return False


class HistoryStore:
    """Rolling price/OI samples + optional sqlite/jsonl under NEXUS_DATA_DIR."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._samples: dict[str, deque[dict[str, Any]]] = {}
        self._mode = "memory"
        self._root: Path | None = None
        self._db_path: Path | None = None
        self._jsonl_path: Path | None = None
        self._schema_version = SCHEMA_VERSION
        self._ttl_ms = DEFAULT_TTL_MS
        self._last_error = ""
        self._persist_writes = 0
        self._persist_errors = 0
        self._started_at = int(time.time() * 1000)
        self._configure()

    def _configure(self) -> None:
        raw = str(os.environ.get("NEXUS_DATA_DIR", "") or "").strip()
        if not raw:
            self._mode = "memory"
            return
        root = Path(raw) / "market_intelligence"
        if not _writable_dir(root):
            self._mode = "memory"
            self._last_error = "nexus_data_dir_not_writable"
            return
        self._root = root
        self._db_path = root / "mi_history.sqlite3"
        self._jsonl_path = root / "mi_events.jsonl"
        try:
            self._init_sqlite()
            self._mode = "sqlite"
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"sqlite_init_failed:{exc}"
            self._mode = "jsonl" if _writable_dir(root) else "memory"

    def _init_sqlite(self) -> None:
        assert self._db_path is not None
        con = sqlite3.connect(str(self._db_path), timeout=5.0)
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS samples (
                  symbol TEXT NOT NULL,
                  ts INTEGER NOT NULL,
                  price REAL,
                  oi REAL,
                  turnover REAL,
                  payload TEXT,
                  PRIMARY KEY (symbol, ts)
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_samples_symbol_ts ON samples(symbol, ts)"
            )
            con.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            con.commit()
        finally:
            con.close()

    @property
    def mode(self) -> str:
        return self._mode

    def status(self) -> dict[str, Any]:
        with self._lock:
            span_ms = 0
            for dq in self._samples.values():
                if len(dq) >= 2:
                    span_ms = max(span_ms, int(dq[-1]["t"]) - int(dq[0]["t"]))
                elif len(dq) == 1:
                    span_ms = max(span_ms, 0)
            return {
                "ok": True,
                "mode": self._mode,
                "persistence": self._mode != "memory",
                "schemaVersion": self._schema_version,
                "ttlMs": self._ttl_ms,
                "sampleCapacityPerSymbol": SAMPLE_CAPACITY_PER_SYMBOL,
                "symbolCount": len(self._samples),
                "sampleCount": sum(len(v) for v in self._samples.values()),
                "historySpanMs": span_ms,
                "root": str(self._root) if self._root else None,
                "persistWrites": self._persist_writes,
                "persistErrors": self._persist_errors,
                "lastError": self._last_error or None,
                "startedAt": self._started_at,
                "secretsStored": False,
                "walletStored": False,
                "ordersStored": False,
                "researchOnly": True,
            }

    def append_sample(
        self,
        symbol: str,
        *,
        price: float | None,
        oi: float | None = None,
        turnover: float | None = None,
        ts: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        sym = symbol.upper().strip()
        if not sym:
            return False
        now = int(ts if ts is not None else time.time() * 1000)
        row = {
            "t": now,
            "price": price,
            "oi": oi,
            "turnover": turnover,
        }
        if extra:
            row["extra"] = _sanitize(extra)
        with self._lock:
            if sym not in self._samples and len(self._samples) >= MAX_SYMBOLS:
                # drop oldest symbol by first sample time
                oldest = min(
                    self._samples.items(),
                    key=lambda kv: int(kv[1][0]["t"]) if kv[1] else now,
                )[0]
                self._samples.pop(oldest, None)
            dq = self._samples.get(sym)
            if dq is None:
                dq = deque(maxlen=SAMPLE_CAPACITY_PER_SYMBOL)
                self._samples[sym] = dq
            # duplicate suppress within 2s same price
            if dq:
                last = dq[-1]
                if now - int(last["t"]) < 2000 and last.get("price") == price and last.get("oi") == oi:
                    return False
                if now < int(last["t"]):
                    return False  # out-of-order
                if now - int(last["t"]) < 4000:
                    # keep-last within short window
                    last.update(row)
                    self._persist_sample(sym, last)
                    return True
            dq.append(row)
            self._prune_ttl(dq, now)
            self._persist_sample(sym, row)
            return True

    def _prune_ttl(self, dq: deque[dict[str, Any]], now: int) -> None:
        cutoff = now - self._ttl_ms
        while dq and int(dq[0]["t"]) < cutoff:
            dq.popleft()

    def get_samples(self, symbol: str, *, limit: int = 100) -> list[dict[str, Any]]:
        sym = symbol.upper().strip()
        lim = max(1, min(int(limit or 100), SAMPLE_CAPACITY_PER_SYMBOL))
        with self._lock:
            dq = self._samples.get(sym)
            if not dq:
                return []
            return list(dq)[-lim:]

    def append_event(self, kind: str, payload: dict[str, Any]) -> None:
        """Append research event to jsonl when persistence available."""
        rec = {
            "kind": kind,
            "ts": int(time.time() * 1000),
            "schemaVersion": SCHEMA_VERSION,
            "payload": _sanitize(payload),
        }
        if self._mode == "memory" or not self._jsonl_path:
            return
        try:
            with self._lock:
                with self._jsonl_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                self._persist_writes += 1
        except Exception as exc:  # noqa: BLE001
            self._persist_errors += 1
            self._last_error = str(exc)

    def _persist_sample(self, symbol: str, row: dict[str, Any]) -> None:
        if self._mode != "sqlite" or not self._db_path:
            if self._mode == "jsonl":
                self.append_event("sample", {"symbol": symbol, **row})
            return
        try:
            con = sqlite3.connect(str(self._db_path), timeout=5.0)
            try:
                con.execute(
                    """
                    INSERT OR REPLACE INTO samples(symbol, ts, price, oi, turnover, payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        int(row["t"]),
                        row.get("price"),
                        row.get("oi"),
                        row.get("turnover"),
                        json.dumps(_sanitize(row), ensure_ascii=False),
                    ),
                )
                # capacity prune
                con.execute(
                    """
                    DELETE FROM samples WHERE symbol = ? AND ts NOT IN (
                      SELECT ts FROM samples WHERE symbol = ?
                      ORDER BY ts DESC LIMIT ?
                    )
                    """,
                    (symbol, symbol, SAMPLE_CAPACITY_PER_SYMBOL),
                )
                cutoff = int(time.time() * 1000) - self._ttl_ms
                con.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
                con.commit()
                self._persist_writes += 1
            finally:
                con.close()
        except Exception as exc:  # noqa: BLE001
            self._persist_errors += 1
            self._last_error = str(exc)


_STORE: HistoryStore | None = None
_STORE_LOCK = threading.Lock()


def get_history_store() -> HistoryStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = HistoryStore()
        return _STORE
