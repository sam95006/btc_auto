"""Runtime identity for frozen Demo observation cohort.

Prefer bake-time / deploy-time commit files over stale env labels.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_STALE_LABELS = frozenset(
    {
        "92a89dfaa8cc",
        "92a89dfaa8cc0000000000000000000000000000",
    }
)


@dataclass
class RuntimeIdentity:
    source_commit: str
    deployment_commit: str
    deployment_run: str
    container_image_digest: str
    container_started_at: str
    runtime_boot_id: str
    policy_bundle_checksum: str
    runtime_artifact_hash: str
    policy_version: str
    schema_version: str
    account_epoch: str
    service_name: str
    identity_captured_at: float
    identity_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_commit": self.source_commit,
            "deployment_commit": self.deployment_commit,
            "deployment_run": self.deployment_run,
            "deploy_run": self.deployment_run,  # alias
            "container_image_digest": self.container_image_digest,
            "container_started_at": self.container_started_at,
            "runtime_boot_id": self.runtime_boot_id,
            "boot_id": self.runtime_boot_id,  # alias
            "policy_bundle_checksum": self.policy_bundle_checksum,
            "runtime_artifact_hash": self.runtime_artifact_hash,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
            "account_epoch": self.account_epoch,
            "service_name": self.service_name,
            "identity_captured_at": self.identity_captured_at,
            "captured_at": self.identity_captured_at,
            "identity_class": self.identity_class,
            "runtime_identity": self.identity_class,
            "identity_method": "bake_file+git+env_fallback",
        }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _resolve_commit(*, data_root: Path) -> tuple[str, str]:
    """Return (commit, source_tag).

    Priority:
      1) Image bake (/app) — authoritative for the running deploy
      2) data_root session bake — used by unit tests / cohort freeze when /app absent
      3) repo/cwd bake files
      4) env / git fallbacks
    """
    candidates: list[tuple[str, str]] = []
    for path in (
        Path("/app/DEPLOYMENT_COMMIT"),
        Path("/app/SOURCE_COMMIT"),
        data_root / "artifacts" / "demo_validation" / "DEPLOYMENT_COMMIT",
        data_root / "DEPLOYMENT_COMMIT",
        data_root / "SOURCE_COMMIT",
        Path(__file__).resolve().parents[2] / "DEPLOYMENT_COMMIT",
        Path(__file__).resolve().parents[2] / "SOURCE_COMMIT",
        Path("DEPLOYMENT_COMMIT"),
        Path("SOURCE_COMMIT"),
    ):
        val = _read_text(path)
        if val:
            candidates.append((val[:64], f"file:{path.name}"))

    env_keys = (
        "NEXUS_SOURCE_COMMIT",
        "NEXUS_DEPLOYMENT_COMMIT",
        "GITHUB_SHA",
        "ZEABUR_GIT_COMMIT",
        "NEXUS_DEPLOYMENT_ID",
    )
    for key in env_keys:
        val = (os.environ.get(key) or "").strip()
        if val:
            candidates.append((val[:64], f"env:{key}"))

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).resolve().parents[2]),
            timeout=3,
        )
        sha = out.decode("utf-8", errors="ignore").strip()
        if sha:
            candidates.append((sha[:64], "git:HEAD"))
    except Exception:
        pass

    for commit, src in candidates:
        short = commit[:12]
        if short in _STALE_LABELS or commit in _STALE_LABELS:
            continue
        if commit and commit != "UNKNOWN":
            return commit, src
    # If only stale labels exist, still return them but mark later as LABEL_STALE.
    if candidates:
        return candidates[0][0], candidates[0][1] + ":stale"
    return "UNKNOWN", "missing"


def classify_identity(commit: str, source: str) -> str:
    short = (commit or "")[:12]
    if not commit or commit == "UNKNOWN":
        return "RUNTIME_IDENTITY_UNKNOWN"
    if short in _STALE_LABELS or commit in _STALE_LABELS or source.endswith(":stale"):
        return "RUNTIME_IDENTITY_LABEL_STALE"
    return "RUNTIME_IDENTITY_CONFIRMED"


def capture_runtime_identity(
    *,
    account_epoch: str,
    policy_version: str,
    schema_version: str,
    service_name: str,
    data_root: Path,
) -> RuntimeIdentity:
    data_root = Path(data_root)
    commit, source = _resolve_commit(data_root=data_root)
    identity_class = classify_identity(commit, source)
    deploy_run = (os.environ.get("NEXUS_DEPLOY_RUN_ID") or os.environ.get("GITHUB_RUN_ID") or "UNKNOWN")[:64]
    boot_id = (os.environ.get("NEXUS_BOOT_ID") or f"boot-{int(time.time())}")[:64]
    image_digest = (
        (os.environ.get("NEXUS_CONTAINER_IMAGE_DIGEST") or os.environ.get("ZEABUR_IMAGE_DIGEST") or "UNKNOWN")
    )[:128]
    started_at = (os.environ.get("NEXUS_CONTAINER_STARTED_AT") or os.environ.get("ZEABUR_DEPLOYED_AT") or "")[:64]
    if not started_at:
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    files = _list_package_files()
    policy_bundle = hashlib.sha256(
        json.dumps({"policy_version": policy_version, "schema_version": schema_version, "files": files}, sort_keys=True).encode()
    ).hexdigest()[:32]
    manifest = {
        "source_commit": commit,
        "deployment_commit": commit,
        "commit_source": source,
        "deployment_run": deploy_run,
        "policy_version": policy_version,
        "schema_version": schema_version,
        "account_epoch": account_epoch,
        "files": files,
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    runtime_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    identity = RuntimeIdentity(
        source_commit=commit,
        deployment_commit=commit,
        deployment_run=deploy_run,
        container_image_digest=image_digest,
        container_started_at=started_at,
        runtime_boot_id=boot_id,
        policy_bundle_checksum=policy_bundle,
        runtime_artifact_hash=runtime_hash,
        policy_version=policy_version,
        schema_version=schema_version,
        account_epoch=account_epoch,
        service_name=service_name,
        identity_captured_at=time.time(),
        identity_class=identity_class,
    )
    try:
        out_dir = data_root / "artifacts" / "demo_validation"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "runtime_identity.json").write_text(
            json.dumps(identity.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        # Bake resolved commit so subsequent restarts do not fall back to stale env.
        if identity_class == "RUNTIME_IDENTITY_CONFIRMED":
            (out_dir / "DEPLOYMENT_COMMIT").write_text(commit + "\n", encoding="utf-8")
            try:
                Path("DEPLOYMENT_COMMIT").write_text(commit + "\n", encoding="utf-8")
            except Exception:
                pass
    except Exception:
        pass
    return identity


def _list_package_files() -> list[str]:
    root = Path(__file__).resolve().parent
    return sorted(p.name for p in root.glob("*.py"))
