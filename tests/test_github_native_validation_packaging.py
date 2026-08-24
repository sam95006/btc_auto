"""GitHub-native Validation packaging — no temp CTX, confirmed service id."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "demo_autonomous_6h_v2_zeabur.yml"
FULL = ROOT / "deploy" / "zeabur_bybit_demo_validation" / "Dockerfile.full_engine"
MINIMAL = ROOT / "deploy" / "zeabur_bybit_demo_validation" / "Dockerfile"
MAP = ROOT / "docs" / "validation" / "SERVICE_ID_MAP.md"

CONFIRMED = "6a82a79aa21454a2cf6b0015"
OBSOLETE = "6a69ad539949111176cefe63"


def test_confirmed_validation_id_in_map() -> None:
    text = MAP.read_text(encoding="utf-8")
    assert CONFIRMED in text
    assert "VALIDATION_SERVICE_ID_CONFIRMED" in text
    assert "**yes**" in text
    assert "OBSOLETE" in text
    assert OBSOLETE in text


def test_full_engine_copies_packaging_from_deploy_folder() -> None:
    text = FULL.read_text(encoding="utf-8")
    assert "COPY deploy/zeabur_bybit_demo_validation/entrypoint.sh ./entrypoint.sh" in text
    assert "COPY deploy/zeabur_bybit_demo_validation/demo_founder_gate.env ./demo_founder_gate.env" in text
    assert "NEXUS_VALIDATION_BOOT=full_engine" in text
    assert "MAINNET=false" in text
    assert "REAL_MONEY=false" in text
    assert "EXCHANGE_WRITE=false" in text
    assert "ARG GITHUB_SHA" in text


def test_minimal_dockerfile_copies_packaging_from_deploy_folder() -> None:
    text = MINIMAL.read_text(encoding="utf-8")
    assert "COPY deploy/zeabur_bybit_demo_validation/entrypoint.sh ./entrypoint.sh" in text
    assert "NEXUS_VALIDATION_BOOT=health" in text
    assert "ARG GITHUB_SHA" in text


def test_full_engine_copy_sources_exist_in_repo() -> None:
    required = [
        ROOT / "app.py",
        ROOT / "run.py",
        ROOT / "gunicorn.conf.py",
        ROOT / "zbpack.json",
        ROOT / "requirements.txt",
        ROOT / "backend",
        ROOT / "config",
        ROOT / "static",
        ROOT / "templates",
        ROOT / "tools" / "ci",
        ROOT / "deploy" / "zeabur_bybit_demo_validation" / "entrypoint.sh",
        ROOT / "deploy" / "zeabur_bybit_demo_validation" / "demo_founder_gate.env",
        ROOT / "deploy" / "zeabur_bybit_demo_validation" / "validation_health_server.py",
    ]
    missing = [str(path) for path in required if not path.exists()]
    assert missing == []


def test_6h_workflow_is_github_native_and_targets_confirmed_service() -> None:
    text = WF.read_text(encoding="utf-8")
    assert f"VALIDATION_SERVICE_ID: {CONFIRMED}" in text
    assert f'default: "{CONFIRMED}"' in text
    assert "CTX=/tmp/6h_v2_ctx" not in text
    assert "CTX=/tmp/12h_full_ctx" not in text
    assert "ZBPACK_DOCKERFILE_PATH" in text
    assert "deploy/zeabur_bybit_demo_validation/Dockerfile.full_engine" in text
    assert "6a3b81652fdef84a45a2a553" in text
    assert "69d559cb2696d526abde8cda" in text
    assert "6a744ba3472e2c91a9e728a8" in text


def test_12h_extended_observation_is_github_native() -> None:
    text = (ROOT / ".github" / "workflows" / "demo_autonomous_12h_v3_extended_observation.yml").read_text(
        encoding="utf-8"
    )
    assert f"VALIDATION_SERVICE_ID: {CONFIRMED}" in text
    assert "CTX=/tmp/12h_v3_ctx" not in text
    assert "ZBPACK_DOCKERFILE_PATH" in text


def test_p1_p2_preservation_report_exists() -> None:
    report = (ROOT / "docs" / "validation" / "P1_P2_REGRESSION_PRESERVATION.md").read_text(encoding="utf-8")
    assert "P1_HISTORICAL_EVIDENCE_PRESERVED" in report
    assert "FULL_P1_RERUN_REQUIRED" in report
    assert "**no**" in report
