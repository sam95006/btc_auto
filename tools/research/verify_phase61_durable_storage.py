"""Phase 6.1 local verify — dedicated research SQLite path + WAL profile."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="nexus_p61_"))
    os.environ["NEXUS_DATA_DIR"] = str(tmp)
    # seed legacy
    legacy = tmp / "nexus_research.db"
    legacy.write_bytes(b"")  # empty; migration still creates dedicated path

    import backend.nexus_research.storage as st

    st._STORE = None
    from backend.nexus_research.storage import get_research_store
    from backend.nexus_research.storage_discovery import discover_storage
    from backend.nexus_research.persistence_validation import create_persistence_probe

    store = get_research_store()
    disc = discover_storage()
    profile = store.sqlite_runtime_profile()
    probe = create_persistence_probe()
    wal = store.wal_checkpoint()
    path = str(store.db_path).replace("\\", "/")
    assert path.endswith("/nexus-research/nexus_research.db"), path
    assert "trading.db" not in path
    assert profile.get("journal_mode") == "wal"
    assert profile.get("foreign_keys") in (1, True)
    assert int(profile.get("busy_timeout_ms") or 0) >= 1000
    assert profile.get("integrity_check") == "ok"
    assert store.schema_version >= 3
    assert disc.get("durableClaim") is False
    assert disc.get("productionPersistenceAvailable") is False
    assert probe.get("probeId")
    assert wal.get("ok") is True
    print("VERIFY_PHASE61_STORAGE_OK")
    print("db=", path)
    print("mode=", disc.get("recommendedMode"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
