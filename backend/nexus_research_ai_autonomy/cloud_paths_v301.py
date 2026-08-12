"""V18.2.30.1 cloud-safe runtime paths — no D:\\NEXUS_RUNTIME hard dependency."""

from __future__ import annotations

import os
import socket
import uuid
from pathlib import Path

# Zeabur volume mount point (canonical).
DEFAULT_DATA_ROOT = Path("/data")
DEFAULT_CAMPAIGN_NAME = "research_v18_2_30"


def runtime_location() -> str:
    """Classify where this process believes it is running."""
    explicit = (os.environ.get("NEXUS_RUNTIME_LOCATION") or "").strip().upper()
    if explicit in {"ZEABUR", "LOCAL", "STOPPED"}:
        return explicit
    markers = (
        os.environ.get("ZEABUR"),
        os.environ.get("ZEABUR_SERVICE_ID"),
        os.environ.get("ZEABUR_PROJECT_ID"),
        os.environ.get("ZEABUR_ENVIRONMENT_ID"),
    )
    if any(str(x or "").strip() for x in markers):
        return "ZEABUR"
    if (os.environ.get("KUBERNETES_SERVICE_HOST") or "").strip():
        return "ZEABUR"
    data = os.environ.get("NEXUS_DATA_ROOT") or ""
    if data.startswith("/data"):
        return "ZEABUR"
    return "LOCAL"


def data_root() -> Path:
    raw = (os.environ.get("NEXUS_DATA_ROOT") or "").strip()
    if raw:
        return Path(raw)
    if runtime_location() == "ZEABUR":
        return DEFAULT_DATA_ROOT
    # Local fallback — prefer env, else /tmp (never require D:\ on cloud).
    return Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp") / "nexus_data"


def campaign_root(*, name: str | None = None) -> Path:
    override = (os.environ.get("NEXUS_CAMPAIGN_ROOT") or "").strip()
    if override:
        return Path(override)
    camp = name or (os.environ.get("NEXUS_CAMPAIGN_NAME") or DEFAULT_CAMPAIGN_NAME)
    return data_root() / "campaigns" / camp


def autonomy_dir(root: Path | None = None) -> Path:
    r = root or campaign_root()
    return r / "autonomy"


def checkpoints_dir(root: Path | None = None) -> Path:
    r = root or campaign_root()
    return r / "checkpoints"


def evidence_dir() -> Path:
    override = (os.environ.get("NEXUS_EVIDENCE_COORDINATOR") or "").strip()
    if override:
        return Path(override)
    return data_root() / "evidence_coordinator"


def lock_dir() -> Path:
    override = (os.environ.get("NEXUS_AUTONOMY_LOCK_DIR") or "").strip()
    if override:
        return Path(override)
    return data_root() / "autonomy" / "locks"


def worker_instance_id() -> str:
    existing = (os.environ.get("NEXUS_WORKER_INSTANCE_ID") or "").strip()
    if existing:
        return existing
    host = socket.gethostname()
    pid = os.getpid()
    stamp = uuid.uuid4().hex[:8]
    wid = f"{host}-{pid}-{stamp}"
    os.environ["NEXUS_WORKER_INSTANCE_ID"] = wid
    return wid


def ensure_writable(path: Path) -> dict[str, object]:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write_probe"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"ok": True, "path": str(path)}
    except OSError as exc:
        return {"ok": False, "path": str(path), "error": type(exc).__name__}


def resolve_demo_env_path() -> Path | None:
    """Prefer Zeabur env vars; optional local .env only if present and allowed."""
    explicit = (os.environ.get("NEXUS_DEMO_ENV_FILE") or "").strip()
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    # Cloud: credentials must already be in process env — do not require a file.
    if runtime_location() == "ZEABUR":
        return None
    allow_local = (os.environ.get("NEXUS_ALLOW_LOCAL_ENV") or "1").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not allow_local:
        return None
    candidates = [
        Path(r"D:\NEXUS\btc_bot\.env"),
        Path.cwd() / ".env",
        Path("/app/.env"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None
