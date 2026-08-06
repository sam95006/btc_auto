"""Regression: private-field scanner must not count probe/deny fixtures as leaks."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_scanner():
    tools_public = str(ROOT / "tools" / "public")
    if tools_public not in sys.path:
        sys.path.insert(0, tools_public)
    # Fresh load so tip edits are visible inside a long pytest session.
    sys.modules.pop("scan_private_field_leaks", None)
    return importlib.import_module("scan_private_field_leaks")


def test_authoritative_scanner_zero_real_leaks_on_tip():
    mod = _load_scanner()
    report = mod.scan_private_field_leaks(ROOT)
    assert report["private_field_leak_count"] == 0, report.get("survivors")
    assert report["ok"] is True
    # Prior false positives must still be seen and classified, not silently dropped.
    fps = report["false_positives_classified"]
    files = {h["file"] for h in fps}
    assert any("security_privacy_redteam/attacks.py" in f for f in files)
    assert any("intelligence_dto_v2/hard_bans.py" in f for f in files)
    assert all(h["classification"] == "SCANNER_FALSE_POSITIVE" for h in fps)


def test_scanner_flags_real_emission_without_probe_context(tmp_path: Path):
    mod = _load_scanner()
    pkg = tmp_path / "backend" / "nexus_public_decision_cloud"
    pkg.mkdir(parents=True)
    (pkg / "routes.py").write_text(
        '''
def member_decision_payload():
    return {"strategy_weights": {"a": 1}, "ok": True}
''',
        encoding="utf-8",
    )
    report = mod.scan_private_field_leaks(tmp_path)
    assert report["private_field_leak_count"] == 1
    survivor = report["survivors"][0]
    assert survivor["field"] == "strategy_weights"
    assert survivor["classification"] == "REAL_LEAK"
    assert "routes.py" in survivor["file"]


def test_scanner_does_not_flag_adversarial_allowlist_probe(tmp_path: Path):
    mod = _load_scanner()
    pkg = tmp_path / "backend" / "nexus_public_intelligence_dto_v2"
    pkg.mkdir(parents=True)
    (pkg / "hard_bans.py").write_text(
        '''
def pass2_adversarial(root):
    # Allow-list must drop unknown keys
    leaked = serialize_allowlist({**clean, "strategy_weights": {"a": 1}})
    if "strategy_weights" in collect_field_names(leaked):
        findings.append("allowlist_leaked_private")
''',
        encoding="utf-8",
    )
    report = mod.scan_private_field_leaks(tmp_path)
    assert report["private_field_leak_count"] == 0
    assert report["scanner_false_positive_count"] >= 1
