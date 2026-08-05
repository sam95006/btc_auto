"""Android build config validation (no Play upload)."""

from __future__ import annotations

from pathlib import Path

from backend.public_mobile_release.hard_bans import BanFinding
from backend.public_mobile_release.package_gate import package_root, repo_root
from backend.public_mobile_release.yaml_lite import load_simple_yaml


def validate_android_config(root: Path | None = None) -> list[BanFinding]:
    root = root or repo_root()
    pkg = package_root(root)
    findings: list[BanFinding] = []
    cfg = load_simple_yaml(pkg / "build/android/build_config.yaml")
    if cfg.get("submission_authorized") is True:
        findings.append(BanFinding("ANDROID_SUBMISSION_FLAG", "build_config", "true"))
    play = cfg.get("play_console") or {}
    for key in ("upload_enabled", "internal_testing_track_upload", "production_track_upload"):
        if play.get(key) is True:
            findings.append(BanFinding("ANDROID_PLAY_UPLOAD", key, "true"))
    gradle = (pkg / "build/android/build.gradle.kts.fragment").read_text(encoding="utf-8")
    for needle in ("SUBMISSION_AUTHORIZED\", \"false\"", "LIVE_BILLING_ENABLED\", \"false\"", "REAL_IAP_PRODUCTS_ENABLED\", \"false\""):
        if needle not in gradle:
            findings.append(BanFinding("ANDROID_BUILDCONFIG_BAN_MISSING", "build.gradle.kts.fragment", needle))
    manifest = (pkg / "build/android/AndroidManifest.xml.fragment").read_text(encoding="utf-8")
    if 'android:value="true"' in manifest and "submission_authorized" in manifest:
        # ensure submission meta is false
        if 'android:name="com.nexus.public.submission_authorized"\n        android:value="false"' not in manifest.replace(
            "\r\n", "\n"
        ):
            if 'submission_authorized"' in manifest and 'android:value="false"' not in manifest:
                findings.append(BanFinding("ANDROID_MANIFEST_SUBMISSION", "manifest", "not false"))
    return findings


def main() -> int:
    findings = validate_android_config()
    if findings:
        for f in findings:
            print(f"FAIL {f.code} {f.path} :: {f.detail}")
        print("ANDROID_CONFIG_FAIL")
        return 1
    print("ANDROID_CONFIG_PASS")
    print("ANDROID_PLAY_UPLOAD_BANNED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
