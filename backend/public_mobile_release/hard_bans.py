"""Hard bans for PUB-L store compliance lane."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REQUIRED_FALSE_FLAGS = (
    "submission_authorized",
    "legal_approval_claimed",
    "live_billing_enabled",
    "real_iap_products_enabled",
    "production_customer_db_enabled",
)

FORBIDDEN_SUBSTRINGS = (
    "upload_to_app_store",
    "upload_to_play_store",
    "fastlane deliver",
    "fastlane_deliver",
    "supply_upload",
    "create_production_customer_db",
    "ENABLE_LIVE_BILLING=true",
    "SUBMISSION_AUTHORIZED=true",
    "REAL_IAP_PRODUCTS_ENABLED=true",
)

FORBIDDEN_STATUS_GLOB = "*_status.json"

PRIVATE_ROUTE_MARKERS = (
    "/private/execution",
    "/private/control-plane",
    "/lesson-memory/",
    "NEXUS_PRIVATE_CONTROL_PLANE_URL",
    "NEXUS_EXECUTION_ENGINE_URL",
    "NEXUS_LESSON_MEMORY_URL",
)

LEGAL_APPROVAL_CLAIM_MARKERS = (
    "legally approved",
    "legal approval granted",
    "counsel has approved",
    "we are compliant with",
)


@dataclass(frozen=True)
class BanFinding:
    code: str
    path: str
    detail: str


def _iter_text_files(root: Path) -> Iterable[Path]:
    skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pyc", ".zip"}:
            continue
        yield path


def _is_negated_ban_context(text_lower: str, needle: str) -> bool:
    """Allow documentation that forbids the action rather than enabling it."""
    if any(
        marker in text_lower
        for marker in (
            "forbidden_ci_steps",
            "forbidden_rollback_actions",
            "hard ban",
            "hard_ban",
            "must not",
            "do not",
            "must remain unused",
            "banned",
            "forbid",
            "rejects",
            "never call",
            "no app store",
            "no google play",
        )
    ):
        # Still fail if clearly enabled as assignment/true
        if f"{needle}=true" in text_lower or f"{needle}: true" in text_lower:
            return False
        if f"run: {needle}" in text_lower or f"runs: {needle}" in text_lower:
            return False
        return True
    return False


def scan_forbidden_substrings(package_root: Path) -> list[BanFinding]:
    findings: list[BanFinding] = []
    for path in _iter_text_files(package_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lower = text.lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            if needle.lower() not in lower:
                continue
            if _is_negated_ban_context(lower, needle.lower()):
                continue
            findings.append(BanFinding("FORBIDDEN_SUBSTRING", str(path), needle))
        for marker in PRIVATE_ROUTE_MARKERS:
            if marker.lower() not in lower:
                continue
            if any(
                m in lower
                for m in (
                    "forbidden",
                    "forbidden_env_names",
                    "forbidden_capabilities",
                    "must remain",
                    "no_",
                    "ban",
                    "hard ban",
                )
            ):
                continue
            findings.append(BanFinding("PRIVATE_ROUTE_EMBED", str(path), marker))
        for claim in LEGAL_APPROVAL_CLAIM_MARKERS:
            if claim not in lower:
                continue
            if any(
                m in lower
                for m in (
                    "no_legal_approval",
                    "not_legal",
                    "claimed: no",
                    "claimed:** no",
                    "approval_claimed: false",
                    "do not claim",
                )
            ):
                continue
            findings.append(BanFinding("LEGAL_APPROVAL_CLAIM", str(path), claim))
    return findings


def scan_status_json(repo_root: Path) -> list[BanFinding]:
    findings: list[BanFinding] = []
    for path in repo_root.glob("**/public_mobile_release/**/*_status.json"):
        findings.append(BanFinding("STATUS_JSON_BANNED", str(path), FORBIDDEN_STATUS_GLOB))
    for path in repo_root.glob("artifacts/**/pub_l*_status.json"):
        findings.append(BanFinding("STATUS_JSON_BANNED", str(path), FORBIDDEN_STATUS_GLOB))
    return findings


def assert_flag_false(mapping: dict, key: str, source: str) -> BanFinding | None:
    if key not in mapping:
        return BanFinding("MISSING_FLAG", source, key)
    val = mapping[key]
    if val is True or val == "true" or val == 1 or val == "1":
        return BanFinding("FLAG_MUST_BE_FALSE", source, key)
    return None


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    package = repo / "public_mobile_release"
    findings = scan_forbidden_substrings(package) + scan_status_json(repo)
    if findings:
        for f in findings:
            print(f"BAN_FAIL {f.code} {f.path} :: {f.detail}")
        return 1
    print("HARD_BANS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
