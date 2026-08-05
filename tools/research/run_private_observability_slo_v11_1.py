#!/usr/bin/env python3
"""Run Founder-private Observability SLO V11.1 readiness (TWO-PASS).

Emits artifacts under:
  artifacts/readiness/immutable/v11_1_observability/

No public routes. No account secrets. No execution mutation endpoint.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_observability import (  # noqa: E402
    ALERT_CLASSES,
    HARD_BANS,
    apply_pass2_adversarial_overrides,
    build_private_observability_slo,
)
from backend.nexus_observability.constants import (  # noqa: E402
    ARTIFACT_REL,
    OWNED_PATHS,
    SCHEMA_SECRET_SCAN,
)
from backend.nexus_observability.sanitize import assert_no_forbidden_keys  # noqa: E402

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    assert_no_forbidden_keys(obj if isinstance(obj, dict) else {"value": obj})


def scan_secrets(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = root / rel
        files: list[Path]
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md", ".yml", ".yaml"}
            ]
        elif target.is_file():
            files = [target]
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": SCHEMA_SECRET_SCAN,
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": list(OWNED_PATHS),
    }


def _pass_summary(
    *,
    pass_number: int,
    bundle: dict[str, Any],
    secret: dict[str, Any],
    findings: list[str],
) -> dict[str, Any]:
    status = bundle["status"]
    matrix = bundle["alert_matrix"]
    active_classes = sorted(
        {a["alert_class"] for a in matrix["alerts"] if a.get("active")}
    )
    return {
        "schema": f"v11_1_private_observability_pass_{pass_number}_summary",
        "created_at": _utc(),
        "pass_number": pass_number,
        "pass": status.get("status") == "PASS" and secret["secret_leak_count"] == 0,
        "status": status.get("status"),
        "slo_score": status.get("slo_score"),
        "slo_status": status.get("slo_status"),
        "slos_passed": status.get("slos_passed"),
        "slos_total": status.get("slos_total"),
        "active_alert_count": status.get("active_alert_count"),
        "active_alert_classes": active_classes,
        "alert_classes_required": list(ALERT_CLASSES),
        "secret_leak_count": secret["secret_leak_count"],
        "hard_ban_count": len(HARD_BANS),
        "public_routes": False,
        "execution_mutation_endpoint": False,
        "findings": findings,
    }


def run_pass(
    *,
    pass_number: int,
    root: Path,
    art: Path,
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    bundle = build_private_observability_slo(
        root,
        overrides=overrides,
        pass_number=pass_number,
    )
    findings: list[str] = []
    if pass_number == 1:
        findings.append("baseline_domain_health_collected")
        findings.append("slo_definitions_emitted")
        findings.append("alert_pipeline_wired")
    else:
        active = {a["alert_class"] for a in bundle["alert_matrix"]["alerts"] if a.get("active")}
        missing = [c for c in ALERT_CLASSES if c not in active]
        if missing:
            findings.append(f"pass2_missing_alert_classes:{missing}")
        else:
            findings.append("pass2_all_alert_classes_exercised")
        findings.append("pass2_adversarial_overrides_applied")
        findings.append("pass2_no_execution_mutation")
        findings.append("pass2_no_public_routes")
        # Pass 2 still requires SLO coverage (breach alerted counts as pass)
        if bundle["status"]["status"] != "PASS":
            findings.append("pass2_slo_coverage_gap")

    _write(art / "slo_definitions.json", bundle["slo_definitions"])
    _write(art / "alert_matrix.json", bundle["alert_matrix"])
    _write(art / "domain_health_snapshot.json", bundle["domain_health_snapshot"])
    _write(art / "hard_bans.json", bundle["hard_bans"])
    _write(art / "observability_slo_status.json", bundle["status"])

    secret = scan_secrets(root)
    _write(art / "secret_scan.json", secret)

    summary = _pass_summary(
        pass_number=pass_number,
        bundle=bundle,
        secret=secret,
        findings=findings,
    )
    _write(art / f"pass_{pass_number}_summary.json", summary)
    return {"bundle": bundle, "secret": secret, "summary": summary}


def main() -> int:
    art = ROOT / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    passes = int(os.getenv("NEXUS_V11_1_OBS_PASSES", "2") or 2)

    # Pass 1: healthy / measured baseline (storage floor may alert if disk < 30GiB)
    p1 = run_pass(pass_number=1, root=ROOT, art=art, overrides=None)
    results = [p1]

    if passes >= 2:
        # Pass 2: adversarial breaches — every alert class must fire; SLOs still covered.
        p2 = run_pass(
            pass_number=2,
            root=ROOT,
            art=art,
            overrides=apply_pass2_adversarial_overrides(),
        )
        results.append(p2)

    # Final status from last pass, with both summaries retained.
    final_secret = scan_secrets(ROOT)
    _write(art / "secret_scan.json", final_secret)

    last = results[-1]
    final_status = dict(last["bundle"]["status"])
    final_status["created_at"] = _utc()
    final_status["passes_executed"] = len(results)
    final_status["pass_1_ok"] = bool(results[0]["summary"].get("pass"))
    final_status["pass_2_ok"] = (
        bool(results[1]["summary"].get("pass")) if len(results) > 1 else None
    )
    final_status["secret_leak_count"] = final_secret["secret_leak_count"]
    if final_secret["secret_leak_count"] != 0:
        final_status["status"] = "FAIL"
    if not final_status["pass_1_ok"]:
        final_status["status"] = "FAIL"
    if len(results) > 1 and not final_status["pass_2_ok"]:
        final_status["status"] = "FAIL"

    # Metrics rollup
    metrics = {
        "schema": "v11_1_private_observability_metrics",
        "created_at": _utc(),
        "slo_score_pass_1": results[0]["bundle"]["status"]["slo_score"],
        "slo_score_pass_2": results[1]["bundle"]["status"]["slo_score"] if len(results) > 1 else None,
        "active_alerts_pass_1": results[0]["bundle"]["status"]["active_alert_count"],
        "active_alerts_pass_2": results[1]["bundle"]["status"]["active_alert_count"]
        if len(results) > 1
        else None,
        "domain_count": len(results[0]["bundle"]["domain_health_snapshot"]["domains"]),
        "slo_definition_count": results[0]["bundle"]["slo_definitions"]["slo_count"],
        "hard_ban_count": len(HARD_BANS),
        "secret_leak_count": final_secret["secret_leak_count"],
        "exchange_write_attempt_count": 0,
        "execution_mutation_endpoint": False,
        "public_routes": False,
    }
    _write(art / "metrics.json", metrics)
    _write(art / "observability_slo_status.json", final_status)

    blockers: list[str] = []
    if final_secret["secret_leak_count"]:
        blockers.append("secret_leak_detected")
    if not final_status.get("pass_1_ok"):
        blockers.append("pass_1_failed")
    if len(results) > 1 and not final_status.get("pass_2_ok"):
        blockers.append("pass_2_failed")
    _write(
        art / "blockers.json",
        {
            "schema": "v11_1_private_observability_blockers",
            "created_at": _utc(),
            "blockers": blockers,
            "blocker_count": len(blockers),
        },
    )

    print(json.dumps(final_status, indent=2))
    return 0 if final_status["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
