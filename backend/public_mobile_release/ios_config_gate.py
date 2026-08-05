"""iOS project/config validation gate (no signed build claim on non-macOS)."""

from __future__ import annotations

import platform
from pathlib import Path

from backend.public_mobile_release.hard_bans import BanFinding
from backend.public_mobile_release.package_gate import package_root, repo_root
from backend.public_mobile_release.yaml_lite import load_simple_yaml


def validate_ios_config(root: Path | None = None) -> tuple[list[BanFinding], str]:
    root = root or repo_root()
    pkg = package_root(root)
    findings: list[BanFinding] = []
    cfg = load_simple_yaml(pkg / "build/ios/build_config.yaml")
    if cfg.get("submission_authorized") is True:
        findings.append(BanFinding("IOS_SUBMISSION_FLAG", "build/ios/build_config.yaml", "true"))
    if (cfg.get("xcode") or {}).get("app_store_connect_upload") is True:
        findings.append(BanFinding("IOS_ASC_UPLOAD", "build/ios/build_config.yaml", "upload true"))
    privacy = pkg / "build/ios/PrivacyInfo.xcprivacy"
    if not privacy.is_file():
        findings.append(BanFinding("MISSING_PRIVACY_MANIFEST", str(privacy), "PrivacyInfo.xcprivacy"))
    export = (pkg / "build/ios/ExportOptions.plist.template").read_text(encoding="utf-8")
    if "app-store" in export and "<string>app-store</string>" in export:
        findings.append(BanFinding("IOS_EXPORT_APP_STORE", "ExportOptions", "app-store"))

    system = platform.system().lower()
    if findings:
        return findings, "IOS_PROJECT_CONFIG_FAIL"
    if system == "darwin":
        # Still do not claim signed build without certs
        return [], "IOS_PROJECT_CONFIG_PASS"
    return [], "IOS_PROJECT_CONFIG_PASS"


def main() -> int:
    findings, status = validate_ios_config()
    print(status)
    if platform.system().lower() != "darwin":
        print("IOS_SIGNED_BUILD_PLATFORM_BLOCKED")
    else:
        print("IOS_SIGNED_BUILD_REQUIRES_CERTS_NOT_RUN")
    for f in findings:
        print(f"FAIL {f.code} {f.path} :: {f.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
