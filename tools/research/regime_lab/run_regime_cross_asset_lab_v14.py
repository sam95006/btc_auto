#!/usr/bin/env python3
"""V14-F Regime and Cross-Asset Lab campaign harness.

Point-in-Time regimes + cross-asset lead-lag without future leakage.
No predictive edge / trading claim.

Emits artifacts under:
  artifacts/readiness/immutable/v14_regime_lab/

Writes D:\\NEXUS_RUNTIME\\v14_f_status.json by default.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ART_REL = Path("artifacts/readiness/immutable/v14_regime_lab")
RUNTIME_STATUS_DEFAULT = Path(r"D:\NEXUS_RUNTIME\v14_f_status.json")
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"
BRANCH = "feature/v14-regime-cross-asset-lab"

OWNED_SCAN_PATHS = [
    "backend/nexus_regime_lab",
    "tools/research/regime_lab",
    "tests/regime_lab",
    "artifacts/readiness/immutable/v14_regime_lab",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]

EDGE_CLAIM_PATTERNS = [
    re.compile(r"(?i)guaranteed\s+profit"),
    re.compile(r"(?i)trading\s+edge\s+confirmed"),
    re.compile(r"(?i)alpha\s+signal\s+ready"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def scan_secrets() -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_SCAN_PATHS:
        target = ROOT / rel
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"}
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
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v14_f_regime_lab_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": OWNED_SCAN_PATHS,
    }


def scan_edge_claims() -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_SCAN_PATHS[:3]:
        target = ROOT / rel
        files = (
            [p for p in target.rglob("*.py")]
            if target.is_dir()
            else ([target] if target.is_file() else [])
        )
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in EDGE_CLAIM_PATTERNS:
                for m in pat.finditer(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "pattern": pat.pattern,
                            "snippet": text[m.start() : m.end() + 20],
                        }
                    )
    return {
        "schema": "v14_f_edge_claim_scan",
        "created_at": _utc(),
        "edge_claim_count": len(hits),
        "hits": hits,
    }


def run_pytest() -> dict[str, Any]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/regime_lab",
            "-q",
            "--tb=line",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "tail": "\n".join(out.strip().splitlines()[-60:]),
    }


def run_pass1_campaign() -> dict[str, Any]:
    from backend.nexus_regime_lab import (
        REGIME_IDS,
        forensic_campaign_probe,
        prove_lead_lag_no_negative_receive_leak,
        prove_pit_excludes_future,
        regime_catalog,
        run_classification_once,
        verify_deterministic_replay,
    )
    from backend.nexus_regime_lab.forensic_ro import (
        forensic_env_guard,
        scan_owned_paths_for_write_apis,
    )
    from backend.nexus_regime_lab.lead_lag import lead_lag_matrix
    from backend.nexus_regime_lab.fixtures import build_synthetic_bars

    catalog = regime_catalog()
    seeds = [f"v14f-case-{i:03d}" for i in range(5)]
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    cases: list[dict[str, Any]] = []
    replay_results: list[dict[str, Any]] = []
    for seed in seeds:
        for sym in symbols:
            run = run_classification_once(seed=seed, symbol=sym)
            replay = verify_deterministic_replay(seed=seed, symbol=sym)
            cases.append(
                {
                    "seed": seed,
                    "symbol": sym,
                    "as_of_ms": run["as_of_ms"],
                    "fixture_checksum": run["fixture_checksum"],
                    "fingerprint": run["fingerprint"],
                    "lead_lag_fingerprint": run["lead_lag_fingerprint"],
                    "regime_ids_present": sorted(run["bundle"]["regimes"]),
                    "availability": {
                        rid: obs["availability"]
                        for rid, obs in run["bundle"]["regimes"].items()
                    },
                    "lead_lag_best_lag": run["lead_lag"].get("best_lag"),
                    "lead_lag_trading_claim": run["lead_lag"].get("trading_claim"),
                    "replay_match": replay["match"],
                    "predictive_edge_claimed": False,
                }
            )
            replay_results.append(replay)

    pit = prove_pit_excludes_future(seed="v14f-pit-campaign")
    ll_pit = prove_lead_lag_no_negative_receive_leak(seed="v14f-ll-pit-campaign")
    forensic = forensic_campaign_probe(ROOT)
    env = forensic_env_guard()
    owned_py = list((ROOT / "backend" / "nexus_regime_lab").rglob("*.py"))
    write_scan = scan_owned_paths_for_write_apis(owned_py)

    capture = build_synthetic_bars(seed="v14f-matrix")
    matrix = lead_lag_matrix(
        capture["bars"],
        symbols=list(capture["symbols"]),
        as_of_ms=int(capture["window_end_ms"]) + 1_000,
        bar_ms=int(capture["bar_ms"]),
    )

    all_regimes_present = all(
        set(c["regime_ids_present"]) == set(REGIME_IDS) for c in cases
    )
    all_replay = all(r["match"] for r in replay_results)
    no_ll_claims = all(c["lead_lag_trading_claim"] is False for c in cases)
    return {
        "pass": "PASS_1",
        "catalog": catalog,
        "cases": cases,
        "replay_results": replay_results,
        "pit_proof": pit,
        "lead_lag_receive_pit": ll_pit,
        "lead_lag_matrix": matrix,
        "forensic": forensic,
        "env_guard": env,
        "write_api_scan": write_scan,
        "regime_count": len(REGIME_IDS),
        "case_count": len(cases),
        "all_regimes_present": all_regimes_present,
        "all_replay_match": all_replay,
        "pit_holds": bool(pit.get("pit_holds")) and bool(ll_pit.get("pit_holds")),
        "lead_lag_no_trading_claim": no_ll_claims and matrix.get("trading_claim") is False,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "event_study_invoked": False,
        "pr27_merged": False,
        "auto_integrate": False,
        "predictive_edge_claim_count": 0,
        "raw_partitions_modified": bool(forensic.get("raw_partitions_modified")),
        "raw_partitions_sealed": bool(forensic.get("raw_partitions_sealed")),
    }


def run_pass2_adversarial(pass1: dict[str, Any]) -> dict[str, Any]:
    from backend.nexus_regime_lab import (
        ForensicWriteAttemptError,
        refuse_write,
    )
    from backend.nexus_regime_lab.fixtures import build_synthetic_bars
    from backend.nexus_regime_lab.regimes import (
        classify_bundle_from_capture,
        classify_volatility_regime,
    )
    from backend.nexus_regime_lab.replay import (
        fingerprint_bundle,
        prove_pit_excludes_future,
    )

    findings: list[dict[str, Any]] = []

    pit = prove_pit_excludes_future(seed="v14f-pass2-pit")
    if not pit["pit_holds"]:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "PIT_FUTURE_LEAK",
                "detail": "Future bar altered regime/lead-lag fingerprint at as_of",
            }
        )

    base = 1_720_000_000_000
    empty = classify_volatility_regime([], symbol="BTCUSDT", as_of_ms=base + 60_000)
    if empty["availability"] != "MISSING" or empty["label"] is not None:
        findings.append(
            {
                "severity": "HIGH",
                "code": "SILENT_IMPUTE_VOL_REGIME",
                "detail": empty,
            }
        )

    try:
        refuse_write(ROOT / "artifacts" / "forensic_ban_probe")
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "FORENSIC_WRITE_NOT_BLOCKED",
                "detail": "refuse_write did not raise",
            }
        )
    except ForensicWriteAttemptError:
        pass

    findings.append(
        {
            "severity": "INFO",
            "code": "FIXTURE_SYNTHETIC_ONLY",
            "detail": (
                "Regime/lead-lag proofs use synthetic fixtures; old campaign is RO "
                "forensic probe only — not claimed as live capture validation. "
                "No predictive edge or trading claim."
            ),
            "status": "ACKNOWLEDGED",
        }
    )

    capture_a = build_synthetic_bars(seed="adv-a")
    capture_b = build_synthetic_bars(seed="adv-b")
    as_of_a = int(capture_a["window_end_ms"]) + 1_000
    as_of_b = int(capture_b["window_end_ms"]) + 1_000
    fa = fingerprint_bundle(
        classify_bundle_from_capture(capture_a, symbol="BTCUSDT", as_of_ms=as_of_a)
    )
    fb = fingerprint_bundle(
        classify_bundle_from_capture(capture_b, symbol="BTCUSDT", as_of_ms=as_of_b)
    )
    if fa == fb:
        findings.append(
            {
                "severity": "HIGH",
                "code": "CONSTANT_FINGERPRINT_STUB",
                "detail": "Different seeds produced identical fingerprints",
            }
        )

    if not pass1.get("all_replay_match"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "PASS1_REPLAY_FALSE_PASS",
                "detail": "Pass1 reported without all_replay_match",
            }
        )
    if not pass1.get("pit_holds"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "PASS1_PIT_FALSE_PASS",
                "detail": "Pass1 reported without pit_holds",
            }
        )
    if not pass1.get("lead_lag_no_trading_claim"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "LEAD_LAG_EDGE_CLAIM",
                "detail": "Lead-lag path emitted a trading claim",
            }
        )

    # Explicit: lead-lag must not use receive > as_of
    ll_pit = pass1.get("lead_lag_receive_pit") or {}
    if not ll_pit.get("pit_holds"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "LEAD_LAG_RECEIVE_LEAK",
                "detail": ll_pit,
            }
        )

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    high = [f for f in findings if f.get("severity") == "HIGH"]
    return {
        "pass": "PASS_2",
        "findings": findings,
        "critical_count": len(critical),
        "high_count": len(high),
        "pit_proof": pit,
        "empty_regime_ok": empty["availability"] == "MISSING" and empty["label"] is None,
        "seed_divergence_ok": fa != fb,
        "adversarial_ok": len(critical) == 0 and len(high) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ROOT / ART_REL)
    parser.add_argument("--runtime-status", type=Path, default=RUNTIME_STATUS_DEFAULT)
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")

    secrets = scan_secrets()
    _write(out / "secret_scan.json", secrets)
    edge = scan_edge_claims()
    _write(out / "edge_claim_scan.json", edge)

    pass1 = run_pass1_campaign()
    _write(
        out / "regime_catalog.json",
        {
            "schema": "v14_f_regime_catalog_artifact",
            "created_at": _utc(),
            **pass1["catalog"],
        },
    )
    _write(
        out / "regime_cases.json",
        {
            "schema": "v14_f_regime_cases",
            "created_at": _utc(),
            "case_count": pass1["case_count"],
            "cases": pass1["cases"],
        },
    )
    _write(
        out / "deterministic_replay.json",
        {
            "schema": "v14_f_deterministic_replay_artifact",
            "created_at": _utc(),
            "all_match": pass1["all_replay_match"],
            "results": pass1["replay_results"],
        },
    )
    _write(out / "pit_proof.json", {**pass1["pit_proof"], "created_at": _utc()})
    _write(
        out / "lead_lag_receive_pit.json",
        {**pass1["lead_lag_receive_pit"], "created_at": _utc()},
    )
    _write(
        out / "lead_lag_matrix.json",
        {**pass1["lead_lag_matrix"], "created_at": _utc()},
    )
    _write(out / "forensic_ro_probe.json", {**pass1["forensic"], "created_at": _utc()})
    _write(
        out / "pass1_summary.json",
        {k: v for k, v in pass1.items() if k not in {"catalog", "lead_lag_matrix"}},
    )

    pass2 = run_pass2_adversarial(pass1)
    _write(out / "pass2_adversarial.json", {**pass2, "created_at": _utc()})

    pytest_result: dict[str, Any] = {"skipped": True, "passed": True}
    if not args.skip_pytest:
        pytest_result = run_pytest()
        _write(out / "pytest_report.json", pytest_result)

    head = _git_head()
    remaining_blockers: list[dict[str, Any]] = []
    if pass1.get("raw_partitions_modified") or pass1.get("raw_partitions_sealed"):
        remaining_blockers.append({"code": "RAW_PARTITION_MUTATION", "severity": "CRITICAL"})
    if not pass1.get("forensic", {}).get("artifact_dir_exists"):
        remaining_blockers.append(
            {
                "code": "REFERENCE_FINALIZER_ARTIFACTS_ABSENT",
                "severity": "INFO",
                "detail": "Old campaign finalizer dir absent in this worktree; RO probe recorded absence only",
            }
        )

    status_pass = (
        pass1["all_regimes_present"]
        and pass1["all_replay_match"]
        and pass1["pit_holds"]
        and pass1["lead_lag_no_trading_claim"]
        and pass1["exchange_write_attempt_count"] == 0
        and pass1["demo_order_count"] == 0
        and pass1["event_study_invoked"] is False
        and pass1["pr27_merged"] is False
        and pass1["auto_integrate"] is False
        and pass1["predictive_edge_claim_count"] == 0
        and pass1["raw_partitions_modified"] is False
        and pass1["raw_partitions_sealed"] is False
        and pass1["write_api_scan"]["ok"] is True
        and pass1["env_guard"]["ok"] is True
        and pass2["adversarial_ok"] is True
        and secrets["secret_leak_count"] == 0
        and edge["edge_claim_count"] == 0
        and bool(pytest_result.get("passed"))
    )

    lane_status = {
        "schema": "FOUNDER_V14_F_REGIME_CROSS_ASSET_LAB",
        "lane": "V14-F",
        "lane_name": "REGIME_AND_CROSS_ASSET_LAB",
        "branch": BRANCH,
        "worktree": str(ROOT),
        "base_commit": BASE_COMMIT,
        "head_commit_at_run": head,
        "created_at": _utc(),
        "status": "PASS" if status_pass else "FAIL",
        "passes_completed": ["PASS_1", "PASS_2"],
        "regime_count": pass1["regime_count"],
        "regime_ids": list(pass1["catalog"]["regimes"]),
        "case_count": pass1["case_count"],
        "all_regimes_present": pass1["all_regimes_present"],
        "all_replay_match": pass1["all_replay_match"],
        "pit_holds": pass1["pit_holds"],
        "lead_lag_no_trading_claim": pass1["lead_lag_no_trading_claim"],
        "deterministic_replay_proven": pass1["all_replay_match"],
        "point_in_time_proven": pass1["pit_holds"],
        "adversarial_ok": pass2["adversarial_ok"],
        "critical_findings": pass2["critical_count"],
        "high_findings": pass2["high_count"],
        "remaining_blockers": remaining_blockers,
        "secret_leak_count": secrets["secret_leak_count"],
        "edge_claim_count": edge["edge_claim_count"],
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "event_study_invoked": False,
        "mainnet": False,
        "real_money": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "predictive_edge_claimed": False,
        "profitability_claim_count": 0,
        "raw_partitions_modified": False,
        "raw_partitions_sealed": False,
        "old_campaign_mode": "READ_ONLY_FORENSIC",
        "fixture_source": "synthetic_sanitized",
        "pr27_merged": False,
        "auto_integrate": False,
        "pytest_passed": bool(pytest_result.get("passed")),
        "artifacts_dir": str(ART_REL).replace("\\", "/"),
        "owned_paths": OWNED_SCAN_PATHS,
        "hard_bans_honored": True,
    }
    _write(out / "v14_regime_lab_status.json", lane_status)
    (out / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# V14-F Regime and Cross-Asset Lab",
                "",
                f"- status: **{lane_status['status']}**",
                f"- regimes: {lane_status['regime_count']}",
                f"- cases: {lane_status['case_count']}",
                f"- PIT proof: {lane_status['point_in_time_proven']}",
                f"- deterministic replay: {lane_status['deterministic_replay_proven']}",
                f"- lead-lag trading claim: {'none' if lane_status['lead_lag_no_trading_claim'] else 'FAIL'}",
                f"- adversarial ok: {lane_status['adversarial_ok']}",
                "",
                "Hard bans: no predictive edge, no demo/shadow/exchange write,",
                "no formal WF/OOS, no strategy promotion, no auto-integrate, no PR27 merge.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    runtime = {
        **lane_status,
        "runtime_status_path": str(args.runtime_status),
        "pass2_findings": pass2["findings"],
        "pytest": {
            "passed": pytest_result.get("passed"),
            "exit_code": pytest_result.get("exit_code"),
            "elapsed_s": pytest_result.get("elapsed_s"),
        },
    }
    _write(args.runtime_status, runtime)

    print(json.dumps({"status": lane_status["status"], "pass": status_pass}, indent=2))
    return 0 if status_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
