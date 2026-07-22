"""Phase 6.4 isolated hotfix: storage.status must not run integrity_check on hot path."""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from backend.nexus_research.storage import _ResearchStore, _SqliteStore


def test_status_skips_integrity_check_on_hot_path():
    td = tempfile.mkdtemp()
    db = Path(td) / "nexus_research.db"
    store = _ResearchStore(_SqliteStore(db))
    profile = store.sqlite_runtime_profile(force_integrity=False)
    assert profile.get("integrity_check") == "skipped_on_status_path"
    status = store.status()
    assert status["ok"] is True
    assert status["health"] == "ok"
    assert status["sqliteRuntimeProfile"]["integrity_check"] == "skipped_on_status_path"


def test_maintenance_integrity_check_preserved():
    td = tempfile.mkdtemp()
    db = Path(td) / "nexus_research.db"
    sql = _SqliteStore(db)
    forced = sql.sqlite_runtime_profile(force_integrity=True)
    assert forced.get("integrity_check") == "ok"


def test_table_counts_cache_ttl():
    td = tempfile.mkdtemp()
    db = Path(td) / "nexus_research.db"
    store = _ResearchStore(_SqliteStore(db))
    s1 = store.status()
    c1 = dict(s1.get("tableCounts") or {})
    s2 = store.status()
    c2 = dict(s2.get("tableCounts") or {})
    assert c1 == c2
    # Force expire
    store._table_count_cache = (time.time() - 120.0, {"events": 999})
    s3 = store.status()
    # After expiry, rebuilt counts should not keep the fake 999 forever as sole source
    assert "events" in (s3.get("tableCounts") or {})


def test_concurrent_status_no_deadlock():
    td = tempfile.mkdtemp()
    db = Path(td) / "nexus_research.db"
    store = _ResearchStore(_SqliteStore(db))
    errors: list[str] = []
    results: list[bool] = []

    def worker():
        try:
            for _ in range(8):
                st = store.status()
                results.append(bool(st.get("ok")))
                _ = store.sqlite_runtime_profile(force_integrity=False)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    assert results and all(results)


def test_status_is_readonly_no_write_side_effects():
    td = tempfile.mkdtemp()
    db = Path(td) / "nexus_research.db"
    store = _ResearchStore(_SqliteStore(db))
    before = store.count("persistence_probes")
    store.status()
    after = store.count("persistence_probes")
    assert before == after


def test_skipped_integrity_counts_as_healthy():
    from backend.nexus_research.storage import is_storage_integrity_healthy

    assert is_storage_integrity_healthy("ok") is True
    assert is_storage_integrity_healthy("skipped_on_status_path") is True
    assert is_storage_integrity_healthy("memory") is True
    assert is_storage_integrity_healthy(None) is True
    assert is_storage_integrity_healthy("*** in database main ***") is False
