import json
import copy
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime

try:
    import msvcrt
except Exception:  # pragma: no cover - non-Windows fallback
    msvcrt = None


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


from backend.core.data_paths import resolve_runtime_db_path
from backend.services.live_snapshot_cache import LiveSnapshotCache


class RuntimeStateStore:
    def __init__(self, db_path=None):
        self.db_path = resolve_runtime_db_path(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._write_lock_path = f"{self.db_path}.snapshot.lock"
        self._live_snapshot = LiveSnapshotCache()
        self._snapshot_flush_seconds = max(
            5.0, float(os.getenv("NEXUS_SNAPSHOT_FLUSH_SECONDS", "15") or 15)
        )
        self._snapshot_last_flush_at = 0.0
        self._init_db()
        try:
            loaded = self._load_snapshot_from_db()
            if loaded:
                self._live_snapshot.put(loaded)
        except Exception:
            pass

    def _run_write(self, operation):
        last_error = None
        for attempt in range(6):
            try:
                with self._lock:
                    cursor = self._conn.cursor()
                    result = operation(cursor)
                    self._conn.commit()
                    return result
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        raise last_error

    def _init_db(self):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_runtime_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    snapshot_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    worker_pid INTEGER,
                    worker_status TEXT,
                    snapshot_version INTEGER NOT NULL DEFAULT 0,
                    last_writer TEXT
                )
                """
            )
            columns = {row["name"] for row in cursor.execute("PRAGMA table_info(nexus_runtime_state)").fetchall()}
            if "snapshot_version" not in columns:
                cursor.execute("ALTER TABLE nexus_runtime_state ADD COLUMN snapshot_version INTEGER NOT NULL DEFAULT 0")
            if "last_writer" not in columns:
                cursor.execute("ALTER TABLE nexus_runtime_state ADD COLUMN last_writer TEXT")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_runtime_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    processed_at TEXT,
                    result_json TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_decision_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    raw_signal TEXT NOT NULL,
                    raw_confidence REAL NOT NULL,
                    adjusted_confidence REAL NOT NULL,
                    quality_score REAL NOT NULL,
                    fleet_score REAL NOT NULL,
                    setup_type TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    context_summary TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    reject_layer TEXT,
                    reject_reason TEXT,
                    position_size REAL NOT NULL,
                    leverage REAL NOT NULL,
                    order_id TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_meetings (
                    id TEXT PRIMARY KEY,
                    meeting_type TEXT NOT NULL,
                    meeting_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    broadcasted INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_station_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    station TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    message TEXT NOT NULL,
                    source TEXT NOT NULL,
                    importance TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    journal_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_trade_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_signal_weight_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    recommendation_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_trade_validation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    validation_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_round_table_decision_memory (
                    meeting_time TEXT PRIMARY KEY,
                    memory_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_decision_traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    trace_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_learning_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    review_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_applied_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fleet TEXT,
                    strategy_key TEXT,
                    patch_json TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_reflection_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    fleet TEXT,
                    symbol TEXT,
                    strategy_key TEXT,
                    reflection_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_micro_validation_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_trade_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    proposal_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_strategy_versions (
                    version_id TEXT PRIMARY KEY,
                    version_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_strategy_rotation_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    suggestion_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_shadow_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_json TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def default_snapshot(self):
        return {
            "system": {
                "running": False,
                "alert_level": "DISCONNECTED",
                "emergency_meeting": False,
                "trading_paused": True,
                "system_health": "WORKER_OFFLINE",
                "current_time": _now(),
                "module_health": {"worker": "OFFLINE"},
                "fleet_status": {
                    fleet: {
                        "status": "DISCONNECTED",
                        "last_signal": "HOLD",
                        "last_reason": "Worker disconnected",
                    }
                    for fleet in ["BTC", "ETH", "SOL", "PEPE"]
                },
            },
            "capital": {
                "total": 0.0,
                "hq_reserve": 0.0,
                "radar_budget": 0.0,
                "active_total": 0.0,
                "realized_pnl": 0.0,
                "fleets": {fleet: {"allocated": 0.0, "available": 0.0, "frozen": 0.0, "realized_pnl": 0.0} for fleet in ["BTC", "ETH", "SOL", "PEPE"]},
                "entries": [],
            },
            "loans": {fleet: {"principal": 0.0, "count": 0, "limit": 0} for fleet in ["BTC", "ETH", "SOL", "PEPE"]},
            "positions": [],
            "pnl": {
                "fleets": {fleet: {"realized": 0.0, "unrealized": 0.0, "total": 0.0} for fleet in ["BTC", "ETH", "SOL", "PEPE"]},
                "total_realized": 0.0,
                "total_unrealized": 0.0,
                "total_pnl": 0.0,
            },
            "orders": [],
            "trades": [],
            "prices": {},
            "news": [],
            "whale": {},
            "funding": {},
            "alerts": [],
            "meetings": [],
            "events": [],
            "daily_report": {},
            "decision_summary": {},
            "decision_audit": [],
            "analytics": {},
            "station_chats": {
                key: []
                for key in ["WORLD", "HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "WHALE", "FUNDING", "RISK"]
            },
            "station_briefings": {},
            "binance_sync": {
                "spot": {},
                "futures": {},
                "last_sync_time": 0,
                "sync_status": "idle",
                "errors": [],
            },
            "learning_status": {
                "trade_journal_count": 0,
                "failure_patterns_count": 0,
                "latest_recommendations": [],
                "disabled_patterns": [],
                "strategy_adaptation": {
                    "generated_at": "",
                    "strategies": {},
                },
            },
            "validation_status": {
                "event_count": 0,
                "approved_count": 0,
                "blocked_count": 0,
                "last_event": None,
                "by_fleet": {},
            },
            "normalized_events": [],
            "agent_advisory": {
                "news_understanding": {},
                "radar_interpretation": {},
                "round_table": {},
                "reflection": {},
                "multi_agent": {},
            },
            "llm_status": {
                "enabled": False,
                "providers": {},
                "routes": {},
                "models": {},
                "cache_entries": 0,
                "tasks": {},
            },
                "account_sync_status": {
                    "spot_connected": False,
                    "futures_connected": False,
                    "spot_truth_mode": "rest_only",
                    "futures_truth_mode": "rest_only",
                    "spot_truth_scope": "stable_only",
                    "spot_allowed_assets": [],
                    "spot_excluded_assets_count": 0,
                    "websocket_status": {
                    "spot": "disconnected",
                    "futures": "disconnected",
                },
                "rest_snapshot_status": {
                    "spot": "idle",
                    "futures": "idle",
                },
                "spot_stream_health": {
                    "status": "disconnected",
                    "status_detail": "",
                    "connected": False,
                    "truth_mode": "stream",
                    "last_sync_time": 0,
                    "listen_key_active": False,
                    "reconnect_attempt": 0,
                    "last_keepalive_time": 0,
                    "last_rest_reconcile_time": 0,
                    "event_counts": {
                        "executionReport": 0,
                        "outboundAccountPosition": 0,
                        "balanceUpdate": 0,
                    },
                    "errors": [],
                },
            },
            "leverage_status": {fleet: {} for fleet in ["BTC", "ETH", "SOL", "PEPE"]},
            "truth_layer_status": {
                "fresh_for_ai": False,
                "stale_reasons": [],
                "price_freshness": {},
                "spot_account_freshness": {"age_ms": 0, "status": "stale"},
                "futures_account_freshness": {"age_ms": 0, "status": "stale"},
                "spot_stream_freshness": {"age_ms": 0, "status": "unknown"},
                "degraded_market_contexts": [],
                "last_truth_update_ms": 0,
            },
            "market_context": {},
            "radar_scan": {
                "generated_at": "",
                "scan_status": "idle",
                "candidates": [],
                "whale_watch": [],
                "market_board": [],
            },
            "portfolio_status": {
                "generated_at": "",
                "margin_balance": 0.0,
                "total_open_notional": 0.0,
                "notional_utilization": 0.0,
                "same_side_concentration": 0.0,
                "reserve_action": "hold",
                "side_totals": {"LONG": 0.0, "SHORT": 0.0},
                "fleet_exposures": {},
                "fleet_restrictions": {},
                "capital_adjustments": {},
            },
            "station_learning_exchange": {
                "generated_at": "",
                "meeting_reference": "",
                "station_shares": [],
                "cross_station_lessons": [],
                "opportunity_board": [],
            },
            "runtime": {
                "single_instance": False,
                "snapshot_version": 0,
                "last_writer": "",
                "updated_at": "",
            },
        }

    def _merge_snapshot_defaults(self, current, defaults):
        if not isinstance(current, dict) or not isinstance(defaults, dict):
            return current
        merged = dict(current)
        for key, default_value in defaults.items():
            if key not in merged:
                merged[key] = default_value
                continue
            current_value = merged[key]
            if isinstance(current_value, dict) and isinstance(default_value, dict):
                merged[key] = self._merge_snapshot_defaults(current_value, default_value)
        return merged

    @contextmanager
    def _write_guard(self):
        if msvcrt is None:  # pragma: no cover - non-Windows fallback
            yield
            return
        os.makedirs(os.path.dirname(self._write_lock_path) or ".", exist_ok=True)
        fh = open(self._write_lock_path, "a+b")
        try:
            for attempt in range(10):
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if attempt == 9:
                        raise
                    time.sleep(0.1 * (attempt + 1))
            yield
        finally:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            fh.close()

    def _load_snapshot_from_db(self):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT snapshot_json FROM nexus_runtime_state WHERE id = 1")
            row = cursor.fetchone()
            if not row:
                return self.default_snapshot()
            try:
                snapshot = json.loads(row["snapshot_json"])
                return self._merge_snapshot_defaults(snapshot, self.default_snapshot())
            except Exception:
                return self.default_snapshot()

    def save_snapshot(
        self,
        snapshot,
        worker_pid=None,
        worker_status="ONLINE",
        writer=None,
        single_instance=False,
        flush_now=False,
    ):
        writer = writer or f"pid:{worker_pid or os.getpid()}"
        payload_snapshot = copy.deepcopy(snapshot or {})
        system_block = dict(payload_snapshot.get("system", {}))
        module_health = dict(system_block.get("module_health", {}))
        module_health["worker"] = worker_status
        system_block["module_health"] = module_health
        payload_snapshot["system"] = system_block
        runtime_block = dict(payload_snapshot.get("runtime", {}))
        runtime_block.update(
            {
                "single_instance": bool(single_instance),
                "last_writer": writer,
                "updated_at": _now(),
            }
        )
        payload_snapshot["runtime"] = runtime_block
        self._live_snapshot.put(payload_snapshot)

        now = time.time()
        should_flush = bool(flush_now) or (now - self._snapshot_last_flush_at) >= self._snapshot_flush_seconds
        if not should_flush:
            return

        def operation(cursor):
            cursor.execute("SELECT snapshot_version FROM nexus_runtime_state WHERE id = 1")
            row = cursor.fetchone()
            next_version = int((row["snapshot_version"] if row and row["snapshot_version"] is not None else 0) or 0) + 1
            db_snapshot = copy.deepcopy(payload_snapshot)
            db_runtime = dict(db_snapshot.get("runtime", {}))
            db_runtime["snapshot_version"] = next_version
            db_snapshot["runtime"] = db_runtime
            payload = json.dumps(db_snapshot, ensure_ascii=False)
            cursor.execute(
                """
                INSERT INTO nexus_runtime_state (id, snapshot_json, updated_at, worker_pid, worker_status, snapshot_version, last_writer)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    snapshot_json=excluded.snapshot_json,
                    updated_at=excluded.updated_at,
                    worker_pid=excluded.worker_pid,
                    worker_status=excluded.worker_status,
                    snapshot_version=excluded.snapshot_version,
                    last_writer=excluded.last_writer
                """,
                (payload, _now(), worker_pid, worker_status, next_version, writer),
            )

        with self._write_guard():
            self._run_write(operation)
        self._snapshot_last_flush_at = now

    def load_snapshot(self):
        cached = self._live_snapshot.get()
        if cached is not None:
            return self._merge_snapshot_defaults(cached, self.default_snapshot())
        return self._load_snapshot_from_db()

    def live_snapshot_meta(self):
        return dict(self._live_snapshot.meta())

    def enqueue_command(self, command, payload=None):
        payload = payload or {}

        def operation(cursor):
            cursor.execute(
                """
                INSERT INTO nexus_runtime_commands (command, payload_json, status, created_at)
                VALUES (?, ?, 'PENDING', ?)
                """,
                (command, json.dumps(payload, ensure_ascii=False), _now()),
            )
            return cursor.lastrowid

        return self._run_write(operation)

    def claim_pending_commands(self, limit=20):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, command, payload_json
                FROM nexus_runtime_commands
                WHERE status='PENDING'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            ids = [row["id"] for row in rows]
            commands = []
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except Exception:
                    payload = {}
                commands.append({"id": row["id"], "command": row["command"], "payload": payload})
        if ids:
            def operation(write_cursor):
                write_cursor.executemany(
                    "UPDATE nexus_runtime_commands SET status='PROCESSING' WHERE id=?",
                    [(item_id,) for item_id in ids],
                )
            self._run_write(operation)
        return commands

    def complete_command(self, command_id, result=None, ok=True):
        def operation(cursor):
            status = "DONE" if ok else "FAILED"
            cursor.execute(
                """
                UPDATE nexus_runtime_commands
                SET status=?, processed_at=?, result_json=?
                WHERE id=?
                """,
                (status, _now(), json.dumps(result or {}, ensure_ascii=False), command_id),
            )
        self._run_write(operation)

    def append_decision_audit(self, record):
        def operation(cursor):
            cursor.execute(
                """
                INSERT INTO nexus_decision_audit (
                    timestamp, symbol, raw_signal, raw_confidence, adjusted_confidence,
                    quality_score, fleet_score, setup_type, market_regime, context_summary,
                    approved, reject_layer, reject_reason, position_size, leverage, order_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("timestamp", _now()),
                    record.get("symbol", ""),
                    record.get("raw_signal", "HOLD"),
                    float(record.get("raw_confidence", 0.0) or 0.0),
                    float(record.get("adjusted_confidence", 0.0) or 0.0),
                    float(record.get("quality_score", 0.0) or 0.0),
                    float(record.get("fleet_score", 0.0) or 0.0),
                    record.get("setup_type", ""),
                    record.get("market_regime", ""),
                    record.get("context_summary", ""),
                    1 if record.get("approved") else 0,
                    record.get("reject_layer"),
                    record.get("reject_reason"),
                    float(record.get("position_size", 0.0) or 0.0),
                    float(record.get("leverage", 0.0) or 0.0),
                    record.get("order_id"),
                ),
            )
        self._run_write(operation)

    def recent_decision_audit(self, limit=200):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM nexus_decision_audit
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def prune_rejected_decision_audits(self, keep_limit=25):
        """Drop blocked audit rows so UI funnel reflects current sandbox state."""

        keep_limit = max(5, int(keep_limit or 25))

        def operation(cursor):
            cursor.execute(
                """
                SELECT id FROM nexus_decision_audit
                WHERE COALESCE(approved, 0) = 1
                ORDER BY id DESC
                LIMIT ?
                """,
                (keep_limit,),
            )
            keep_approved = [int(row["id"]) for row in cursor.fetchall()]
            cursor.execute(
                """
                DELETE FROM nexus_decision_audit
                WHERE COALESCE(approved, 0) = 0
                """
            )
            if keep_approved:
                placeholders = ",".join("?" for _ in keep_approved)
                cursor.execute(
                    f"""
                    DELETE FROM nexus_decision_audit
                    WHERE COALESCE(approved, 0) = 1
                      AND id NOT IN ({placeholders})
                    """,
                    keep_approved,
                )

        self._run_write(operation)

    def append_meeting(self, meeting):
        def operation(cursor):
            cursor.execute(
                """
                INSERT OR REPLACE INTO nexus_meetings (id, meeting_type, meeting_json, created_at, broadcasted)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    meeting.get("meeting_id"),
                    meeting.get("type", ""),
                    json.dumps(meeting, ensure_ascii=False),
                    meeting.get("created_at", _now()),
                    1 if meeting.get("broadcasted") else 0,
                ),
            )
        self._run_write(operation)

    def recent_meetings(self, limit=80):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT meeting_json
                FROM nexus_meetings
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            items = []
            for row in rows:
                try:
                    items.append(json.loads(row["meeting_json"]))
                except Exception:
                    pass
            return items

    def append_station_chat(self, message):
        def operation(cursor):
            cursor.execute(
                """
                INSERT INTO nexus_station_chats (timestamp, station, speaker, message, source, importance)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.get("timestamp", _now()),
                    message.get("station", ""),
                    message.get("speaker", ""),
                    message.get("message", ""),
                    message.get("source", ""),
                    message.get("importance", "INFO"),
                ),
            )
        self._run_write(operation)

    def recent_station_chats(self, limit=400):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT timestamp, station, speaker, message, source, importance
                FROM nexus_station_chats
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            grouped = {
                key: []
                for key in ["WORLD", "HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "WHALE", "FUNDING", "RISK"]
            }
            for row in rows:
                item = dict(row)
                grouped.setdefault(item["station"], []).append(item)
            for station in grouped:
                grouped[station].reverse()
            return grouped

    def append_trade_journal(self, journal):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_trade_journal (timestamp, journal_json) VALUES (?, ?)",
                (journal.get("timestamp", _now()), json.dumps(journal, ensure_ascii=False)),
            )
        self._run_write(operation)

    def append_trade_result(self, result):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_trade_results (timestamp, result_json) VALUES (?, ?)",
                (result.get("timestamp", _now()), json.dumps(result, ensure_ascii=False)),
            )
        self._run_write(operation)

    def append_reflection_record(self, record):
        payload = dict(record or {})

        def operation(cursor):
            cursor.execute(
                """
                INSERT INTO nexus_reflection_records (timestamp, fleet, symbol, strategy_key, reflection_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.get("timestamp", _now()),
                    str(payload.get("fleet") or ""),
                    str(payload.get("symbol") or ""),
                    str(payload.get("strategy_key") or ""),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

        self._run_write(operation)

    def recent_reflection_records(self, limit=50):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT reflection_json FROM nexus_reflection_records ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [json.loads(row["reflection_json"]) for row in cursor.fetchall()]

    def append_signal_weight_recommendation(self, recommendation):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_signal_weight_recommendations (timestamp, recommendation_json) VALUES (?, ?)",
                (recommendation.get("timestamp", _now()), json.dumps(recommendation, ensure_ascii=False)),
            )
        self._run_write(operation)

    def append_trade_validation_event(self, validation):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_trade_validation_events (timestamp, validation_json) VALUES (?, ?)",
                (validation.get("timestamp", _now()), json.dumps(validation, ensure_ascii=False)),
            )
        self._run_write(operation)

    def save_round_table_decision_memory(self, memory):
        def operation(cursor):
            cursor.execute(
                """
                INSERT OR REPLACE INTO nexus_round_table_decision_memory (meeting_time, memory_json, timestamp)
                VALUES (?, ?, ?)
                """,
                (
                    memory.get("meeting_time"),
                    json.dumps(memory, ensure_ascii=False),
                    memory.get("timestamp", _now()),
                ),
            )
        self._run_write(operation)

    def recent_trade_journal(self, limit=200):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT journal_json FROM nexus_trade_journal ORDER BY id DESC LIMIT ?", (limit,))
            return [json.loads(row["journal_json"]) for row in cursor.fetchall()]

    def recent_trade_results(self, limit=200):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT result_json FROM nexus_trade_results ORDER BY id DESC LIMIT ?", (limit,))
            return [json.loads(row["result_json"]) for row in cursor.fetchall()]

    def recent_signal_weight_recommendations(self, limit=50):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT recommendation_json FROM nexus_signal_weight_recommendations ORDER BY id DESC LIMIT ?", (limit,))
            return [json.loads(row["recommendation_json"]) for row in cursor.fetchall()]

    def recent_trade_validation_events(self, limit=200):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT validation_json FROM nexus_trade_validation_events ORDER BY id DESC LIMIT ?", (limit,))
            return [json.loads(row["validation_json"]) for row in cursor.fetchall()]

    def clear_negative_trade_results(self):
        """Remove loss rows so backtest/learning cooldown stops blocking testnet trials."""

        def operation(cursor):
            cursor.execute("SELECT id, result_json FROM nexus_trade_results")
            delete_ids = []
            for row in cursor.fetchall():
                try:
                    payload = json.loads(row["result_json"])
                except Exception:
                    continue
                if float(payload.get("pnl") or 0.0) < 0:
                    delete_ids.append(int(row["id"]))
            if not delete_ids:
                return 0
            placeholders = ",".join("?" for _ in delete_ids)
            cursor.execute(f"DELETE FROM nexus_trade_results WHERE id IN ({placeholders})", delete_ids)
            return len(delete_ids)

        return self._run_write(operation) or 0

    def prune_trade_validation_events(self, keep_limit=80):
        keep_limit = max(10, int(keep_limit or 80))

        def operation(cursor):
            cursor.execute("SELECT id FROM nexus_trade_validation_events ORDER BY id DESC LIMIT ?", (keep_limit,))
            keep_ids = [int(row["id"]) for row in cursor.fetchall()]
            if not keep_ids:
                return
            placeholders = ",".join("?" for _ in keep_ids)
            cursor.execute(
                f"DELETE FROM nexus_trade_validation_events WHERE id NOT IN ({placeholders})",
                keep_ids,
            )

        self._run_write(operation)

    def recent_round_table_decision_memory(self, limit=40):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT memory_json FROM nexus_round_table_decision_memory ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [json.loads(row["memory_json"]) for row in cursor.fetchall()]

    def append_decision_trace(self, record):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_decision_traces (timestamp, trace_json) VALUES (?, ?)",
                (record.get("timestamp", _now()), json.dumps(record, ensure_ascii=False)),
            )
        self._run_write(operation)

    def append_decision_traces_batch(self, records):
        rows = [dict(item or {}) for item in (records or []) if item]
        if not rows:
            return 0

        def operation(cursor):
            cursor.executemany(
                "INSERT INTO nexus_decision_traces (timestamp, trace_json) VALUES (?, ?)",
                [
                    (row.get("timestamp", _now()), json.dumps(row, ensure_ascii=False))
                    for row in rows
                ],
            )
            return len(rows)

        return self._run_write(operation) or 0

    def recent_decision_traces(self, limit=100):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT trace_json FROM nexus_decision_traces ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [json.loads(row["trace_json"]) for row in cursor.fetchall()]

    def append_learning_review(self, item):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_learning_reviews (timestamp, status, review_json) VALUES (?, ?, ?)",
                (
                    item.get("timestamp", _now()),
                    item.get("status", "draft"),
                    json.dumps(item, ensure_ascii=False),
                ),
            )
            return cursor.lastrowid

        return self._run_write(operation)

    def update_learning_review_status(self, review_id, status, note=""):
        def operation(cursor):
            cursor.execute("SELECT review_json FROM nexus_learning_reviews WHERE id=?", (review_id,))
            row = cursor.fetchone()
            if not row:
                return
            payload = json.loads(row["review_json"])
            payload["status"] = status
            payload["review_note"] = note
            cursor.execute(
                "UPDATE nexus_learning_reviews SET status=?, review_json=? WHERE id=?",
                (status, json.dumps(payload, ensure_ascii=False), review_id),
            )

        self._run_write(operation)

    def recent_learning_reviews(self, limit=50, status=None):
        with self._lock:
            cursor = self._conn.cursor()
            if status:
                cursor.execute(
                    """
                    SELECT id, review_json FROM nexus_learning_reviews
                    WHERE status=? ORDER BY id DESC LIMIT ?
                    """,
                    (status, limit),
                )
            else:
                cursor.execute(
                    "SELECT id, review_json FROM nexus_learning_reviews ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            items = []
            for row in cursor.fetchall():
                try:
                    payload = json.loads(row["review_json"])
                    payload["id"] = row["id"]
                    items.append(payload)
                except Exception:
                    pass
            return items

    def upsert_applied_learning_patch(self, patch):
        def operation(cursor):
            cursor.execute(
                """
                INSERT INTO nexus_applied_learning (fleet, strategy_key, patch_json, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    patch.get("fleet"),
                    patch.get("strategy_key"),
                    json.dumps(patch, ensure_ascii=False),
                    patch.get("applied_at", _now()),
                ),
            )

        self._run_write(operation)

    def list_applied_learning_patches(self, limit=50):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT patch_json FROM nexus_applied_learning ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [json.loads(row["patch_json"]) for row in cursor.fetchall()]

    def applied_learning_for_fleet(self, fleet, strategy_key=None):
        fleet = str(fleet or "").upper()
        patches = self.list_applied_learning_patches(limit=200)
        matched = []
        for patch in patches:
            if str(patch.get("fleet") or "").upper() != fleet:
                continue
            if strategy_key and patch.get("strategy_key") not in (strategy_key, None):
                continue
            matched.append(patch)
        return matched

    def append_trade_proposal(self, proposal):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_trade_proposals (timestamp, proposal_json) VALUES (?, ?)",
                (proposal.get("timestamp", _now()), json.dumps(proposal, ensure_ascii=False)),
            )

        self._run_write(operation)

    def recent_trade_proposals(self, limit=50):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT proposal_json FROM nexus_trade_proposals ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [json.loads(row["proposal_json"]) for row in cursor.fetchall()]

    def register_strategy_version(self, version):
        def operation(cursor):
            cursor.execute(
                """
                INSERT OR REPLACE INTO nexus_strategy_versions (version_id, version_json, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    version.get("version_id"),
                    json.dumps(version, ensure_ascii=False),
                    version.get("created_at", _now()),
                ),
            )

        self._run_write(operation)

    def list_strategy_versions(self):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT version_json FROM nexus_strategy_versions ORDER BY created_at DESC")
            return [json.loads(row["version_json"]) for row in cursor.fetchall()]

    def append_strategy_rotation_suggestion(self, suggestion):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_strategy_rotation_suggestions (timestamp, suggestion_json) VALUES (?, ?)",
                (suggestion.get("timestamp", _now()), json.dumps(suggestion, ensure_ascii=False)),
            )

        self._run_write(operation)

    def recent_strategy_rotation_suggestions(self, limit=20):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT suggestion_json FROM nexus_strategy_rotation_suggestions ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [json.loads(row["suggestion_json"]) for row in cursor.fetchall()]

    def append_shadow_session(self, entry):
        def operation(cursor):
            cursor.execute(
                "INSERT INTO nexus_shadow_sessions (timestamp, session_json) VALUES (?, ?)",
                (entry.get("timestamp", _now()), json.dumps(entry, ensure_ascii=False)),
            )

        self._run_write(operation)

    def recent_shadow_sessions(self, limit=50):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT session_json FROM nexus_shadow_sessions ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [json.loads(row["session_json"]) for row in cursor.fetchall()]

    def load_micro_validation_state(self):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT state_json FROM nexus_micro_validation_state WHERE id=1")
            row = cursor.fetchone()
            if not row:
                return {}
            try:
                return json.loads(row["state_json"] or "{}")
            except Exception:
                return {}

    def save_micro_validation_state(self, state):
        payload = dict(state or {})

        def operation(cursor):
            cursor.execute(
                """
                INSERT INTO nexus_micro_validation_state (id, state_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (json.dumps(payload, ensure_ascii=False), payload.get("updated_at") or _now()),
            )

        self._run_write(operation)


runtime_store = RuntimeStateStore()
