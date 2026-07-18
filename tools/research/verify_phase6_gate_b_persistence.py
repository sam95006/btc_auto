#!/usr/bin/env python3
"""verify_phase6_gate_b_persistence.py

Phase 6 Gate B — Persistence verification script.

Checks:
  1. storage_discovery contains no secret values
  2. SQLite migrations are idempotent (run twice, version stable)
  3. append + query round-trip for typed and legacy tables
  4. Research DB path is NOT trading.db
  5. memory fallback works (no NEXUS_DATA_DIR)
  6. persist_validation_marker idempotency
  7. Pagination helper returns correct metadata

Exits with VERDICT=PASS or VERDICT=FAIL printed to stdout.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PASS = "PASS"
FAIL = "FAIL"
_results: list[dict[str, Any]] = []


def check(name: str, fn) -> bool:
    try:
        fn()
        _results.append({"check": name, "result": PASS})
        print(f"  [PASS] {name}")
        return True
    except AssertionError as exc:
        _results.append({"check": name, "result": FAIL, "reason": str(exc)})
        print(f"  [FAIL] {name}: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        _results.append({"check": name, "result": FAIL, "reason": traceback.format_exc()})
        print(f"  [FAIL] {name}: {exc}")
        return False


def _cleanup_store(mod_ref) -> None:
    """Close SQLite connection and reset singleton so temp dirs can be cleaned up."""
    if mod_ref._STORE is not None:
        try:
            mod_ref._STORE.close()
        except Exception:  # noqa: BLE001
            pass
    mod_ref._STORE = None


# ─────────────────────────────────────────────────────────────────────────────
# Check 1 — storage_discovery: no secret values exposed
# ─────────────────────────────────────────────────────────────────────────────

def _check_no_secret_leak():
    from backend.nexus_research.storage_discovery import discover_storage

    # Inject a fake secret to confirm it is never returned
    fake_secret = f"FAKE_SECRET_{uuid.uuid4().hex}"
    os.environ["NEXUS_RESEARCH_DATABASE_URL"] = fake_secret
    try:
        report = discover_storage()
    finally:
        del os.environ["NEXUS_RESEARCH_DATABASE_URL"]

    report_str = json.dumps(report)
    assert fake_secret not in report_str, (
        f"Secret value leaked into discovery report: found '{fake_secret}'"
    )
    # envPresence should show True for NEXUS_RESEARCH_DATABASE_URL (it was set)
    assert report["envPresence"]["NEXUS_RESEARCH_DATABASE_URL"] is True
    # tradingDbPath if present must not equal research db path
    assert report["researchIsolationRequired"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — SQLite migrations are idempotent
# ─────────────────────────────────────────────────────────────────────────────

def _check_migration_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["NEXUS_DATA_DIR"] = tmp
        os.environ["NEXUS_RESEARCH_STORAGE_MODE"] = "sqlite"
        try:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            store1 = _s.get_research_store()
            v1 = store1.schema_version

            # Force rebuild (simulates second startup)
            _cleanup_store(_s)
            store2 = _s.get_research_store()
            v2 = store2.schema_version

            assert v1 == v2, f"Migration not idempotent: v1={v1} v2={v2}"
            from backend.nexus_research.storage import SCHEMA_VERSION
            assert v1 == SCHEMA_VERSION, f"Version mismatch: got {v1}, expected {SCHEMA_VERSION}"
        finally:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            del os.environ["NEXUS_DATA_DIR"]
            del os.environ["NEXUS_RESEARCH_STORAGE_MODE"]


# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — append + query round-trip (typed tables + legacy kv)
# ─────────────────────────────────────────────────────────────────────────────

def _check_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["NEXUS_DATA_DIR"] = tmp
        os.environ["NEXUS_RESEARCH_STORAGE_MODE"] = "sqlite"
        try:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            store = _s.get_research_store()

            # Typed table: domain_events
            eid = str(uuid.uuid4())
            store.append("domain_events", {"event_id": eid, "event_type": "TEST", "tag": "verify"})
            rows = store.query("domain_events", limit=10)
            assert any(r.get("event_id") == eid for r in rows), "domain_events round-trip failed"

            # Typed table: sim_orders
            oid = str(uuid.uuid4())
            store.append("sim_orders", {"order_id": oid, "symbol": "BTCUSDT", "side": "BUY", "status": "open"})
            rows = store.query("sim_orders", limit=10)
            assert any(r.get("order_id") == oid for r in rows), "sim_orders round-trip failed"

            # Legacy kv table
            store.append("legacy_custom", {"val": "hello"})
            rows = store.query("legacy_custom", limit=10)
            assert len(rows) >= 1 and rows[0].get("val") == "hello", "legacy kv round-trip failed"
        finally:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            del os.environ["NEXUS_DATA_DIR"]
            del os.environ["NEXUS_RESEARCH_STORAGE_MODE"]


# ─────────────────────────────────────────────────────────────────────────────
# Check 4 — research DB path ≠ trading.db
# ─────────────────────────────────────────────────────────────────────────────

def _check_not_trading_db():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["NEXUS_DATA_DIR"] = tmp
        os.environ["NEXUS_RESEARCH_STORAGE_MODE"] = "sqlite"
        try:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            store = _s.get_research_store()
            db_path = store.db_path or ""
            assert "nexus_research.db" in db_path, f"Unexpected DB filename: {db_path}"
            assert "trading" not in Path(db_path).name.lower(), (
                f"Research DB file appears to be trading.db: {db_path}"
            )
        finally:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            del os.environ["NEXUS_DATA_DIR"]
            del os.environ["NEXUS_RESEARCH_STORAGE_MODE"]


# ─────────────────────────────────────────────────────────────────────────────
# Check 5 — memory fallback works without NEXUS_DATA_DIR
# ─────────────────────────────────────────────────────────────────────────────

def _check_memory_fallback():
    saved = os.environ.pop("NEXUS_DATA_DIR", None)
    saved_mode = os.environ.pop("NEXUS_RESEARCH_STORAGE_MODE", None)
    try:
        import backend.nexus_research.storage as _s
        _cleanup_store(_s)
        store = _s.get_research_store()
        assert store.backend_type == "memory", f"Expected memory, got {store.backend_type}"
        store.append("test_mem", {"x": 42})
        rows = store.query("test_mem")
        assert len(rows) >= 1 and rows[0].get("x") == 42
    finally:
        import backend.nexus_research.storage as _s
        _cleanup_store(_s)
        if saved is not None:
            os.environ["NEXUS_DATA_DIR"] = saved
        if saved_mode is not None:
            os.environ["NEXUS_RESEARCH_STORAGE_MODE"] = saved_mode


# ─────────────────────────────────────────────────────────────────────────────
# Check 6 — persist_validation_marker idempotency
# ─────────────────────────────────────────────────────────────────────────────

def _check_validation_marker_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["NEXUS_DATA_DIR"] = tmp
        os.environ["NEXUS_RESEARCH_STORAGE_MODE"] = "sqlite"
        try:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            store = _s.get_research_store()
            mid = f"marker_{uuid.uuid4().hex}"

            store.persist_validation_marker(mid, "PERSISTENCE_VALIDATION", {"test": True})
            store.persist_validation_marker(mid, "PERSISTENCE_VALIDATION", {"test": True})  # duplicate

            count = store.count("persistence_validation_markers")
            assert count == 1, f"Idempotency failed: expected 1 marker, got {count}"
        finally:
            import backend.nexus_research.storage as _s
            _cleanup_store(_s)
            del os.environ["NEXUS_DATA_DIR"]
            del os.environ["NEXUS_RESEARCH_STORAGE_MODE"]


# ─────────────────────────────────────────────────────────────────────────────
# Check 7 — paginate helper metadata
# ─────────────────────────────────────────────────────────────────────────────

def _check_pagination():
    saved = os.environ.pop("NEXUS_DATA_DIR", None)
    saved_mode = os.environ.pop("NEXUS_RESEARCH_STORAGE_MODE", None)
    try:
        import backend.nexus_research.storage as _s
        _cleanup_store(_s)
        store = _s.get_research_store()
        for i in range(7):
            eid = str(uuid.uuid4())
            store.append("domain_events", {"event_id": eid, "event_type": "PAGE_TEST", "tag": "pg"})
        page = store.paginate("domain_events", page=1, page_size=3)
        assert page["total"] >= 7, f"total={page['total']}"
        assert len(page["rows"]) == 3
        assert page["hasMore"] is True
    finally:
        import backend.nexus_research.storage as _s
        _cleanup_store(_s)
        if saved is not None:
            os.environ["NEXUS_DATA_DIR"] = saved
        if saved_mode is not None:
            os.environ["NEXUS_RESEARCH_STORAGE_MODE"] = saved_mode


# ─────────────────────────────────────────────────────────────────────────────
# Check 8 — status() returns required Phase 6 fields
# ─────────────────────────────────────────────────────────────────────────────

def _check_status_fields():
    saved = os.environ.pop("NEXUS_DATA_DIR", None)
    saved_mode = os.environ.pop("NEXUS_RESEARCH_STORAGE_MODE", None)
    try:
        import backend.nexus_research.storage as _s
        _cleanup_store(_s)
        store = _s.get_research_store()
        status = store.status()
        required_keys = {
            "storageMode", "durableClaim", "volumeConfirmed",
            "lastMigrationVersion", "health", "researchOnly",
            "production_persistence_available",
        }
        missing = required_keys - status.keys()
        assert not missing, f"status() missing keys: {missing}"
        assert status["researchOnly"] is True
    finally:
        import backend.nexus_research.storage as _s
        _cleanup_store(_s)
        if saved is not None:
            os.environ["NEXUS_DATA_DIR"] = saved
        if saved_mode is not None:
            os.environ["NEXUS_RESEARCH_STORAGE_MODE"] = saved_mode


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("NEXUS Phase 6 Gate B — Persistence Verification")
    print("=" * 60)

    checks = [
        ("1. No secret leak in storage_discovery", _check_no_secret_leak),
        ("2. SQLite migrations idempotent", _check_migration_idempotent),
        ("3. Append + query round-trip", _check_roundtrip),
        ("4. Research DB ≠ trading.db", _check_not_trading_db),
        ("5. Memory fallback works", _check_memory_fallback),
        ("6. persist_validation_marker idempotent", _check_validation_marker_idempotent),
        ("7. Pagination helper metadata", _check_pagination),
        ("8. status() has required Phase 6 fields", _check_status_fields),
    ]

    passed = 0
    failed = 0
    for name, fn in checks:
        ok = check(name, fn)
        if ok:
            passed += 1
        else:
            failed += 1

    print("-" * 60)
    print(f"  Passed: {passed} / {len(checks)}")
    if failed:
        print(f"  Failed: {failed}")

    verdict = PASS if failed == 0 else FAIL
    print(f"\nVERDICT={verdict}")
    return 0 if verdict == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
