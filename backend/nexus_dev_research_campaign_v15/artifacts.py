"""Immutable artifact writer for V15-C — NEVER writes *_status.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_dev_research_campaign_v15.constants import ARTIFACT_DIRNAME, OWNED_PATHS
from backend.nexus_dev_research_campaign_v15.hard_bans import assert_no_status_json


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    if path.name.endswith("status.json") or path.name.endswith("_status.json"):
        raise RuntimeError(f"HARD BAN: refusing to write status json: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_immutable_artifacts(
    report: dict[str, Any],
    adversarial_passes: list[dict[str, Any]],
    *,
    root: Path,
) -> dict[str, Path]:
    out = root / "artifacts" / "readiness" / "immutable" / ARTIFACT_DIRNAME
    out.mkdir(parents=True, exist_ok=True)

    # Strip bulky trade samples from evaluations for catalog-sized JSON.
    evaluations_compact = []
    for e in report.get("evaluations") or []:
        row = {k: v for k, v in e.items() if k not in {"trades_sample", "net_series"}}
        row["net_series_len"] = len(e.get("net_series") or [])
        evaluations_compact.append(row)

    paths: dict[str, Path] = {}
    paths["campaign_report"] = out / "campaign_report.json"
    _write(
        paths["campaign_report"],
        {
            **{k: v for k, v in report.items() if k != "evaluations"},
            "evaluations": evaluations_compact,
            "created_at": _utc(),
        },
    )
    paths["label_histogram"] = out / "label_histogram.json"
    _write(
        paths["label_histogram"],
        {
            "schema": "v15_c_label_histogram",
            "created_at": _utc(),
            "label_histogram": report.get("label_histogram"),
            "allowed_labels": report.get("label_histogram") and sorted((report.get("label_histogram") or {}).keys()),
            "qualification_ready_count": 0,
        },
    )
    paths["evaluations"] = out / "evaluations.json"
    _write(
        paths["evaluations"],
        {
            "schema": "v15_c_evaluations",
            "created_at": _utc(),
            "mechanism_count": report.get("mechanism_count"),
            "evaluations": evaluations_compact,
        },
    )
    paths["multiple_testing"] = out / "multiple_testing.json"
    _write(paths["multiple_testing"], {**report.get("multiple_testing", {}), "created_at": _utc()})
    paths["data_provenance"] = out / "data_provenance.json"
    _write(
        paths["data_provenance"],
        {
            "schema": "v15_c_data_provenance",
            "created_at": _utc(),
            "data_lineage": report.get("data_lineage"),
            "fixture_used": report.get("fixture_used"),
            "fixture_never_called_real": True,
            "development_interval_id": report.get("development_interval_id"),
            "panel_digest": report.get("panel_digest"),
            "provenance": report.get("data_provenance"),
            "oos_consumed": False,
        },
    )
    paths["universe_regime"] = out / "universe_regime_partitions.json"
    _write(
        paths["universe_regime"],
        {
            "schema": "v15_c_universe_regime",
            "created_at": _utc(),
            "dynamic_universe": report.get("dynamic_universe"),
            "regime_partition": report.get("regime_partition"),
        },
    )
    # Adversarial passes (not status.json)
    for i, adv in enumerate(adversarial_passes, start=1):
        key = f"adversarial_pass_{i}"
        paths[key] = out / f"adversarial_pass_{i}.json"
        _write(paths[key], {**adv, "created_at": _utc()})

    paths["blockers"] = out / "blockers.json"
    _write(
        paths["blockers"],
        {
            "schema": "v15_c_blockers",
            "created_at": _utc(),
            "blockers": [
                {
                    "blocker_id": "QUALIFICATION_NOT_AUTHORIZED",
                    "detail": "qualification_ready_count forced 0; no QUALIFIED/profitability claims",
                },
                {
                    "blocker_id": "OOS_AND_FORMAL_WF_BANNED",
                    "detail": "development-classified interval only; untouched OOS sealed",
                },
                {
                    "blocker_id": "NO_STATUS_JSON",
                    "detail": "V15-C emits campaign artifacts only; no *_status.json",
                },
                {
                    "blocker_id": "NO_AUTO_INTEGRATE",
                    "detail": "lane artifacts only; coordinator must not auto-integrate",
                },
            ],
            "qualification_ready_count": 0,
        },
    )
    paths["readme"] = out / "README.md"
    hist = report.get("label_histogram") or {}
    paths["readme"].write_text(
        "\n".join(
            [
                "# V15-C Real Development Research Campaign",
                "",
                f"- data_lineage: `{report.get('data_lineage')}`",
                f"- fixture_used: `{report.get('fixture_used')}` (fixtures are NEVER called real)",
                f"- mechanism_count: {report.get('mechanism_count')}",
                f"- mechanism_family_count: {report.get('mechanism_family_count')}",
                f"- label_histogram: `{json.dumps(hist, sort_keys=True)}`",
                "- qualification_ready_count: **0**",
                "- No QUALIFIED / profitability claims",
                "- No untouched OOS consumption",
                "- No `*_status.json` files in this lane",
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = assert_no_status_json(out)
    if not scan["ok"]:
        raise RuntimeError(f"status json leaked into artifacts: {scan['offenders']}")

    # Guard owned artifact tree naming
    for p in out.rglob("*"):
        if p.is_file() and ("status.json" in p.name):
            raise RuntimeError(f"HARD BAN violated: {p}")

    _ = OWNED_PATHS
    return paths
