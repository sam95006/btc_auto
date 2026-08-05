"""PUB-G UI data contract and traceability tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_ui_trace.ast_guard import scan_forbidden_imports
from backend.nexus_public_ui_trace.bindings import assert_bindings_complete, binding_rows
from backend.nexus_public_ui_trace.component_catalog import (
    UI_COMPONENT_CATALOG,
    pages_covered,
    required_kinds_present,
)
from backend.nexus_public_ui_trace.constants import COMPONENT_KINDS, REQUIRED_COUNTERS
from backend.nexus_public_ui_trace.negative_fixtures import (
    binding_with_private_field,
    binding_with_stale_without_indicator,
    binding_with_unavailable_fabrication,
    binding_with_unmapped,
    binding_with_visible_mock,
)
from backend.nexus_public_ui_trace.public_dto_registry import assert_registry_allowlisted
from backend.nexus_public_ui_trace.two_pass import run_two_pass_verification
from backend.nexus_public_ui_trace.verifier import compute_counters, verify_ui_data_traceability


def test_registry_allowlisted() -> None:
    assert_registry_allowlisted()


def test_catalog_covers_required_kinds_and_pages() -> None:
    assert required_kinds_present()
    assert COMPONENT_KINDS.issubset({c.kind for c in UI_COMPONENT_CATALOG})
    required_pages = {
        "Home",
        "Market Overview",
        "Decision Feed",
        "Decision Detail",
        "Evidence",
        "Counter Evidence",
        "Risk Conditions",
        "Thesis Monitor",
        "Alerts",
        "Decision Memory",
        "Outcome Review",
        "NEX AI Conversation",
        "Membership",
        "Account",
        "Privacy",
        "Account Deletion",
        "Notification Settings",
    }
    assert required_pages.issubset(pages_covered())


def test_bindings_complete_and_rows_nonempty() -> None:
    assert_bindings_complete()
    rows = binding_rows()
    assert len(rows) >= len(UI_COMPONENT_CATALOG)
    assert {r["kind"] for r in rows} == set(COMPONENT_KINDS)


def test_live_verify_all_counters_zero() -> None:
    result = verify_ui_data_traceability(mode="LIVE")
    assert result["status"] == "PASS"
    for key in REQUIRED_COUNTERS:
        assert result["counters"][key] == 0, key


def test_two_pass_matches() -> None:
    result = run_two_pass_verification(mode="LIVE")
    assert result["two_pass_status"] == "PASS"
    assert result["counters_match"] is True
    assert result["observed"] == result["required"]


def test_negative_visible_mock() -> None:
    c = compute_counters(binding_with_visible_mock(), mode="LIVE")
    assert c.visible_mock_value_count >= 1


def test_negative_unmapped() -> None:
    c = compute_counters(binding_with_unmapped(), mode="LIVE")
    assert c.unmapped_live_component_count >= 1


def test_negative_private_field() -> None:
    c = compute_counters(binding_with_private_field(), mode="LIVE")
    assert c.private_field_binding_count >= 1


def test_negative_stale_without_indicator() -> None:
    c = compute_counters(binding_with_stale_without_indicator(), mode="LIVE")
    assert c.stale_without_indicator >= 1


def test_negative_unavailable_fabrication() -> None:
    c = compute_counters(binding_with_unavailable_fabrication(), mode="LIVE")
    assert c.unavailable_fabrication >= 1


def test_ast_guard_clean() -> None:
    assert scan_forbidden_imports(ROOT) == []


def test_gate_script_pass() -> None:
    script = ROOT / "tools" / "public_v1" / "run_ui_data_traceability_gate.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["gate_status"] == "PASS"
    assert payload["status_json_written"] is False
    assert payload["visible_mock_value_count"] == 0
    assert payload["unmapped_live_component_count"] == 0
    assert payload["private_field_binding_count"] == 0
    assert payload["stale_without_indicator"] == 0
    assert payload["unavailable_fabrication"] == 0


def test_no_status_json_artifact_created(tmp_path: Path) -> None:
    # Gate must not write *_status.json into the repo.
    before = {p.name for p in ROOT.rglob("*_status.json") if "node_modules" not in p.parts}
    script = ROOT / "tools" / "public_v1" / "run_ui_data_traceability_gate.py"
    subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, check=True)
    after = {p.name for p in ROOT.rglob("*_status.json") if "node_modules" not in p.parts}
    assert after == before
