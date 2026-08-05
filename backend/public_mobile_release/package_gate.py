"""Package completeness + ban flag gate for PUB-L."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.public_mobile_release.hard_bans import (
    REQUIRED_FALSE_FLAGS,
    BanFinding,
    assert_flag_false,
    scan_forbidden_substrings,
    scan_status_json,
)
from backend.public_mobile_release.yaml_lite import load_simple_yaml

REQUIRED_RELATIVE_PATHS = (
    "README.md",
    "HARD_BANS.md",
    "identifiers/app_ids.yaml",
    "build/ios/build_config.yaml",
    "build/ios/PrivacyInfo.xcprivacy",
    "build/ios/Info.plist.fragment",
    "build/ios/ExportOptions.plist.template",
    "build/android/build_config.yaml",
    "build/android/AndroidManifest.xml.fragment",
    "build/android/build.gradle.kts.fragment",
    "build/android/proguard-rules.pro",
    "signing/signing_abstraction.yaml",
    "signing/README.md",
    "env/environments.yaml",
    "env/env.public.dev.example",
    "env/env.public.staging.example",
    "env/env.public.prod.example",
    "privacy/data_inventory.yaml",
    "privacy/data_safety_draft.md",
    "privacy/financial_disclosure_draft.md",
    "privacy/age_rating_draft.md",
    "deletion/account_deletion_architecture.md",
    "deletion/web_deletion_request.md",
    "deletion/deletion_api_contract.yaml",
    "subscriptions/entitlement_architecture.md",
    "subscriptions/purchase_verification.md",
    "subscriptions/restore_cancel_refund_states.yaml",
    "regional/feature_flags.yaml",
    "review/demo_mode.md",
    "review/reviewer_notes_draft.md",
    "ops/incident_response.md",
    "ops/release_rollback.md",
    "ci/pipeline_spec.yaml",
)

YAML_FLAG_FILES = (
    "identifiers/app_ids.yaml",
    "build/ios/build_config.yaml",
    "build/android/build_config.yaml",
    "signing/signing_abstraction.yaml",
    "env/environments.yaml",
    "privacy/data_inventory.yaml",
    "deletion/deletion_api_contract.yaml",
    "subscriptions/restore_cancel_refund_states.yaml",
    "regional/feature_flags.yaml",
    "ci/pipeline_spec.yaml",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def package_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / "public_mobile_release"


def check_required_files(pkg: Path) -> list[BanFinding]:
    findings: list[BanFinding] = []
    for rel in REQUIRED_RELATIVE_PATHS:
        path = pkg / rel
        if not path.is_file():
            findings.append(BanFinding("MISSING_REQUIRED_FILE", str(path), rel))
    return findings


def _collect_flags(data: Any, out: dict[str, Any]) -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            if k in REQUIRED_FALSE_FLAGS or k in {
                "publish_to_stores",
                "upload_enabled",
                "app_store_connect_upload",
                "play_console",
            }:
                out[k] = v
            if k == "play_console" and isinstance(v, dict):
                out["upload_enabled"] = v.get("upload_enabled")
                out["production_track_upload"] = v.get("production_track_upload")
            _collect_flags(v, out)
    elif isinstance(data, list):
        for item in data:
            _collect_flags(item, out)


def check_yaml_flags(pkg: Path) -> list[BanFinding]:
    findings: list[BanFinding] = []
    for rel in YAML_FLAG_FILES:
        path = pkg / rel
        data = load_simple_yaml(path)
        flags: dict[str, Any] = {}
        _collect_flags(data, flags)
        for key in REQUIRED_FALSE_FLAGS:
            if key in flags:
                finding = assert_flag_false(flags, key, rel)
                if finding:
                    findings.append(finding)
        for key in (
            "publish_to_stores",
            "upload_enabled",
            "app_store_connect_upload",
            "production_track_upload",
            "internal_testing_track_upload",
        ):
            if key in flags:
                finding = assert_flag_false(flags, key, rel)
                if finding:
                    findings.append(finding)
        # identifiers + env must declare submission_authorized
        if rel in {"identifiers/app_ids.yaml", "env/environments.yaml", "ci/pipeline_spec.yaml"}:
            if "submission_authorized" not in data and "submission_authorized" not in flags:
                findings.append(BanFinding("MISSING_FLAG", rel, "submission_authorized"))
    return findings


def check_privacy_manifest(pkg: Path) -> list[BanFinding]:
    findings: list[BanFinding] = []
    path = pkg / "build/ios/PrivacyInfo.xcprivacy"
    text = path.read_text(encoding="utf-8")
    if "NSPrivacyTracking" not in text:
        findings.append(BanFinding("PRIVACY_MANIFEST_INCOMPLETE", str(path), "NSPrivacyTracking"))
    if "<true/>" in text.split("NSPrivacyTracking")[1].split("</")[0] if "NSPrivacyTracking" in text else "":
        # Tracking must be false in draft posture
        chunk = text.split("NSPrivacyTracking", 1)[1][:80]
        if "<true/>" in chunk:
            findings.append(BanFinding("PRIVACY_TRACKING_MUST_BE_FALSE", str(path), "NSPrivacyTracking"))
    if "NSPrivacyCollectedDataTypes" not in text:
        findings.append(
            BanFinding("PRIVACY_MANIFEST_INCOMPLETE", str(path), "NSPrivacyCollectedDataTypes")
        )
    return findings


def check_export_options(pkg: Path) -> list[BanFinding]:
    findings: list[BanFinding] = []
    path = pkg / "build/ios/ExportOptions.plist.template"
    text = path.read_text(encoding="utf-8")
    if "<string>app-store</string>" in text:
        findings.append(BanFinding("IOS_EXPORT_APP_STORE_BANNED", str(path), "method=app-store"))
    if "<string>development</string>" not in text and "<string>debugging</string>" not in text:
        findings.append(BanFinding("IOS_EXPORT_METHOD_UNSAFE", str(path), "expected development"))
    return findings


def check_env_examples(pkg: Path) -> list[BanFinding]:
    findings: list[BanFinding] = []
    forbidden = (
        "BYBIT_API_KEY",
        "BINANCE_API_KEY",
        "NEXUS_PRIVATE_CONTROL_PLANE_URL",
        "NEXUS_EXECUTION_ENGINE_URL",
        "NEXUS_LESSON_MEMORY_URL",
    )
    for name in (
        "env.public.dev.example",
        "env.public.staging.example",
        "env.public.prod.example",
    ):
        path = pkg / "env" / name
        text = path.read_text(encoding="utf-8")
        for key in forbidden:
            # allow mention after FORBIDDEN comment
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith(f"{key}="):
                    findings.append(BanFinding("FORBIDDEN_ENV_ASSIGNMENT", str(path), key))
        if "NEXUS_PUBLIC_SUBMISSION_AUTHORIZED=0" not in text and "SUBMISSION_AUTHORIZED=0" not in text:
            if "NEXUS_PUBLIC_SUBMISSION_AUTHORIZED=0" not in text:
                findings.append(
                    BanFinding("MISSING_SUBMISSION_BAN_ENV", str(path), "NEXUS_PUBLIC_SUBMISSION_AUTHORIZED=0")
                )
        if "NEXUS_PUBLIC_LIVE_BILLING=0" not in text:
            findings.append(BanFinding("MISSING_BILLING_BAN_ENV", str(path), "NEXUS_PUBLIC_LIVE_BILLING=0"))
    return findings


def run_package_gate(root: Path | None = None) -> list[BanFinding]:
    root = root or repo_root()
    pkg = package_root(root)
    findings: list[BanFinding] = []
    findings.extend(check_required_files(pkg))
    findings.extend(check_yaml_flags(pkg))
    findings.extend(check_privacy_manifest(pkg))
    findings.extend(check_export_options(pkg))
    findings.extend(check_env_examples(pkg))
    findings.extend(scan_forbidden_substrings(pkg))
    findings.extend(scan_status_json(root))
    return findings


def main() -> int:
    findings = run_package_gate()
    if findings:
        for f in findings:
            print(f"GATE_FAIL {f.code} {f.path} :: {f.detail}")
        print(f"PACKAGE_GATE_FAIL count={len(findings)}")
        return 1
    print("PACKAGE_GATE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
