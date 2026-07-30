"""Runtime identity for frozen 6H observation cohort."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RuntimeIdentity:
    deployment_commit: str
    deploy_run: str
    policy_version: str
    schema_version: str
    account_epoch: str
    boot_id: str
    runtime_artifact_hash: str
    service_name: str
    captured_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployment_commit": self.deployment_commit,
            "deploy_run": self.deploy_run,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
            "account_epoch": self.account_epoch,
            "boot_id": self.boot_id,
            "runtime_artifact_hash": self.runtime_artifact_hash,
            "service_name": self.service_name,
            "captured_at": self.captured_at,
            "identity_method": "git_sha+deploy_run+boot+manifest_hash",
        }


def capture_runtime_identity(
    *,
    account_epoch: str,
    policy_version: str,
    schema_version: str,
    service_name: str,
    data_root: Path,
) -> RuntimeIdentity:
    commit = (
        (os.environ.get("NEXUS_DEPLOYMENT_ID") or "").strip()
        or (os.environ.get("GITHUB_SHA") or "").strip()
        or (os.environ.get("ZEABUR_GIT_COMMIT") or "").strip()
        or "UNKNOWN"
    )[:64]
    deploy_run = (os.environ.get("NEXUS_DEPLOY_RUN_ID") or os.environ.get("GITHUB_RUN_ID") or "UNKNOWN")[:64]
    boot_id = (os.environ.get("NEXUS_BOOT_ID") or f"boot-{int(time.time())}")[:64]
    manifest = {
        "commit": commit,
        "deploy_run": deploy_run,
        "policy_version": policy_version,
        "schema_version": schema_version,
        "account_epoch": account_epoch,
        "files": _list_package_files(),
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    runtime_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    try:
        (data_root / "artifacts" / "demo_validation").mkdir(parents=True, exist_ok=True)
        (data_root / "artifacts" / "demo_validation" / "runtime_identity.json").write_text(
            json.dumps({**manifest, "runtime_artifact_hash": runtime_hash}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        pass
    return RuntimeIdentity(
        deployment_commit=commit,
        deploy_run=deploy_run,
        policy_version=policy_version,
        schema_version=schema_version,
        account_epoch=account_epoch,
        boot_id=boot_id,
        runtime_artifact_hash=runtime_hash,
        service_name=service_name,
        captured_at=time.time(),
    )


def _list_package_files() -> list[str]:
    root = Path(__file__).resolve().parent
    names: list[str] = []
    for p in sorted(root.glob("*.py")):
        names.append(p.name)
    return names
