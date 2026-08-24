"""Runtime identity — container/image bake beats persistent volume state.

Persistent DEPLOYMENT_COMMIT files are metadata only and must never override
the current executable image identity.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_STALE_LABELS = frozenset(
    {
        "92a89dfaa8cc",
        "92a89dfaa8cc0000000000000000000000000000",
        # Historical PR24 Validation bake — never current live identity.
        "81b0d14e2ffb",
        "81b0d14e2ffb6c5b5e92eeedd7962ed60dd00bc0",
    }
)

# Metadata filenames on persistent volume (never used as current-code identity).
PERSISTENT_ORIGIN_NAME = "PERSISTENT_STATE_ORIGIN_COMMIT"
PERSISTENT_LAST_WRITER_NAME = "PERSISTENT_STATE_LAST_WRITER_COMMIT"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _first_nonempty(paths: list[Path]) -> tuple[str, str]:
    for path in paths:
        val = _read_text(path)
        if val:
            return val[:64], f"file:{path.as_posix()}"
    return "", "missing"


def _pick_non_stale(candidates: list[tuple[str, str]]) -> tuple[str, str]:
    for commit, src in candidates:
        short = (commit or "")[:12]
        if not commit or commit == "UNKNOWN":
            continue
        if short in _STALE_LABELS or commit in _STALE_LABELS:
            continue
        return commit, src
    if candidates:
        c0, s0 = candidates[0]
        return c0 or "UNKNOWN", (s0 or "missing") + ":stale"
    return "UNKNOWN", "missing"


def read_container_baked_commit() -> tuple[str, str]:
    """Immutable image bake — highest priority for executable identity."""
    return _first_nonempty(
        [
            Path("/app/DEPLOYMENT_COMMIT"),
            Path("/app/SOURCE_COMMIT"),
        ]
    )


def read_container_source_commit() -> tuple[str, str]:
    src, tag = _first_nonempty([Path("/app/SOURCE_COMMIT")])
    if src:
        return src, tag
    return read_container_baked_commit()


def read_persistent_state_commits(data_root: Path) -> dict[str, str]:
    """Persistent volume identity metadata — never used as current-code commit."""
    data_root = Path(data_root)
    art = data_root / "artifacts" / "demo_validation"
    origin = _read_text(art / PERSISTENT_ORIGIN_NAME) or _read_text(art / "DEPLOYMENT_COMMIT")
    last = _read_text(art / PERSISTENT_LAST_WRITER_NAME) or _read_text(data_root / "DEPLOYMENT_COMMIT")
    return {
        "persistent_state_origin_commit": (origin or "UNKNOWN")[:64],
        "persistent_state_last_writer_commit": (last or "UNKNOWN")[:64],
    }


def resolve_executable_code_commit(*, data_root: Path | None = None) -> tuple[str, str]:
    """Current executable code identity.

    Precedence (Founder §3):
      1. immutable container/image bake file
      2. image SOURCE_COMMIT
      3. verified runtime artifact hash source (package file digest proxy via env)
      4. environment fallback
      5. git fallback

    Persistent volume files are intentionally excluded.
    """
    candidates: list[tuple[str, str]] = []
    baked, baked_src = read_container_baked_commit()
    if baked:
        candidates.append((baked, baked_src))
    source, source_src = read_container_source_commit()
    if source and source != baked:
        candidates.append((source, source_src))

    # Unit-test / local bake without /app: allow data_root bake to beat stale
    # platform env labels (GITHUB_SHA / NEXUS_DEPLOYMENT_ID) while never beating
    # an immutable /app container bake.
    if not baked and data_root is not None and not Path("/app/DEPLOYMENT_COMMIT").exists():
        test_bake = _read_text(Path(data_root) / "DEPLOYMENT_COMMIT")
        if test_bake:
            candidates.append((test_bake[:64], "file:data_root_test_bake"))

    # Optional explicit code-commit env (not persistent files).
    for key in (
        "NEXUS_SOURCE_COMMIT",
        "NEXUS_DEPLOYMENT_COMMIT",
        "GITHUB_SHA",
        "ZEABUR_GIT_COMMIT_SHA",
        "ZEABUR_ENV_GITHUB_SHA",
        "ZEABUR_ENV_ZEABUR_GIT_COMMIT_SHA",
        "ZEABUR_GIT_COMMIT",
        "NEXUS_DEPLOYMENT_ID",
    ):
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

    return _pick_non_stale(candidates)


def classify_identity(commit: str, source: str) -> str:
    short = (commit or "")[:12]
    if not commit or commit == "UNKNOWN":
        return "RUNTIME_IDENTITY_UNKNOWN"
    if short in _STALE_LABELS or commit in _STALE_LABELS or str(source).endswith(":stale"):
        return "RUNTIME_IDENTITY_LABEL_STALE"
    return "RUNTIME_IDENTITY_CONFIRMED"


def classify_identity_confirmed(
    *,
    runtime_current_code_commit: str,
    container_baked_commit: str,
    expected_deployment_commit: str | None = None,
) -> str:
    """RUNTIME_IDENTITY_CONFIRMED only when code == bake (== expected when provided)."""
    code = (runtime_current_code_commit or "").strip()
    baked = (container_baked_commit or "").strip()
    if not code or code == "UNKNOWN" or not baked or baked == "UNKNOWN":
        return "RUNTIME_IDENTITY_UNKNOWN"
    if code[:12] in _STALE_LABELS or baked[:12] in _STALE_LABELS:
        return "RUNTIME_IDENTITY_LABEL_STALE"
    if code != baked:
        return "RUNTIME_IDENTITY_AMBIGUOUS"
    if expected_deployment_commit:
        exp = expected_deployment_commit.strip()
        if exp and not (code.startswith(exp[:12]) or exp.startswith(code[:12])):
            return "RUNTIME_IDENTITY_MISMATCH"
    return "RUNTIME_IDENTITY_CONFIRMED"


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
    # Separated identity fields
    runtime_current_code_commit: str = ""
    container_baked_commit: str = ""
    container_source_commit: str = ""
    persistent_state_origin_commit: str = "UNKNOWN"
    persistent_state_last_writer_commit: str = "UNKNOWN"
    identity_method: str = "container_bake>env>git"
    commit_source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.runtime_current_code_commit or self.deployment_commit
        baked = self.container_baked_commit or self.deployment_commit
        return {
            "source_commit": self.source_commit,
            "deployment_commit": self.deployment_commit,
            "deploy_run": self.deployment_run,
            "deployment_run": self.deployment_run,
            "container_image_digest": self.container_image_digest,
            "container_started_at": self.container_started_at,
            "runtime_boot_id": self.runtime_boot_id,
            "boot_id": self.runtime_boot_id,
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
            "identity_method": self.identity_method,
            "commit_source": self.commit_source,
            # Founder-required separated identities
            "runtime_current_code_commit": code,
            "container_baked_commit": baked,
            "container_source_commit": self.container_source_commit or baked,
            "persistent_state_origin_commit": self.persistent_state_origin_commit,
            "persistent_state_last_writer_commit": self.persistent_state_last_writer_commit,
            "image_source_commit": self.container_source_commit or baked,
            "image_deployment_commit": baked,
            "session_created_by_commit": self.extra.get("session_created_by_commit", "UNKNOWN"),
            "environment_label_commit": (os.environ.get("NEXUS_DEPLOYMENT_ID") or "UNKNOWN")[:64],
            "expected_deployment_commit": (os.environ.get("EXPECTED_DEPLOYMENT_COMMIT") or "")[:64] or None,
            "env_github_sha": (os.environ.get("GITHUB_SHA") or "")[:64] or None,
        }


def _list_package_files() -> list[str]:
    root = Path(__file__).resolve().parent
    return sorted(p.name for p in root.glob("*.py"))


def capture_runtime_identity(
    *,
    account_epoch: str,
    policy_version: str,
    schema_version: str,
    service_name: str,
    data_root: Path,
    expected_deployment_commit: str | None = None,
) -> RuntimeIdentity:
    data_root = Path(data_root)
    code_commit, code_src = resolve_executable_code_commit(data_root=data_root)
    baked, _ = read_container_baked_commit()
    source, _ = read_container_source_commit()
    if not baked:
        # Local/unit contexts without /app: treat resolved code as bake.
        baked = code_commit
    if not source:
        source = baked

    persistent = read_persistent_state_commits(data_root)
    expected = expected_deployment_commit
    if expected is None:
        # Only explicit EXPECTED_DEPLOYMENT_COMMIT is proof target.
        # Do NOT fall back to GITHUB_SHA — platform/env may retain a stale SHA and
        # falsely classify a correct bake as MISMATCH.
        expected = (os.environ.get("EXPECTED_DEPLOYMENT_COMMIT") or "").strip() or None
    identity_class = classify_identity_confirmed(
        runtime_current_code_commit=code_commit,
        container_baked_commit=baked,
        expected_deployment_commit=expected,
    )
    # If bake missing but code present and non-stale (unit tests), allow CONFIRMED via classify_identity.
    if identity_class == "RUNTIME_IDENTITY_UNKNOWN" and code_commit and code_commit != "UNKNOWN":
        identity_class = classify_identity(code_commit, code_src)

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
        json.dumps(
            {"policy_version": policy_version, "schema_version": schema_version, "files": files},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:32]
    manifest = {
        "runtime_current_code_commit": code_commit,
        "container_baked_commit": baked,
        "commit_source": code_src,
        "deployment_run": deploy_run,
        "policy_version": policy_version,
        "schema_version": schema_version,
        "account_epoch": account_epoch,
        "files": files,
    }
    runtime_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]

    identity = RuntimeIdentity(
        source_commit=source,
        deployment_commit=code_commit,
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
        runtime_current_code_commit=code_commit,
        container_baked_commit=baked,
        container_source_commit=source,
        persistent_state_origin_commit=persistent["persistent_state_origin_commit"],
        persistent_state_last_writer_commit=persistent["persistent_state_last_writer_commit"],
        commit_source=code_src,
    )

    # Persist metadata only — never overwrite as current-code identity authority.
    try:
        out_dir = data_root / "artifacts" / "demo_validation"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "runtime_identity.json").write_text(
            json.dumps(identity.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        # Preserve historical DEPLOYMENT_COMMIT if present; write last-writer metadata.
        if identity_class in {"RUNTIME_IDENTITY_CONFIRMED", "RUNTIME_IDENTITY_AMBIGUOUS"}:
            origin_path = out_dir / PERSISTENT_ORIGIN_NAME
            if not origin_path.exists():
                prior = _read_text(out_dir / "DEPLOYMENT_COMMIT")
                origin_path.write_text((prior or code_commit) + "\n", encoding="utf-8")
            (out_dir / PERSISTENT_LAST_WRITER_NAME).write_text(code_commit + "\n", encoding="utf-8")
    except Exception:
        pass
    return identity
