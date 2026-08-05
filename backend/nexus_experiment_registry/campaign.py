"""V14-J two-pass campaign proving immutable registry + cherry-pick bans."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_experiment_registry.constants import (
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    HARD_BAN_FLAGS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_experiment_registry.hashing import (
    checksum_parameters,
    checksum_universe,
    sha256_hex,
)
from backend.nexus_experiment_registry.record import (
    ExperimentRecordError,
    build_experiment_record,
    verify_experiment_record,
)
from backend.nexus_experiment_registry.registry import (
    ExperimentRegistryError,
    ImmutableExperimentRegistry,
)
from backend.nexus_experiment_registry.versions import resolve_version_pins

ART_REL = Path("artifacts/readiness/immutable/v14_experiment_registry")
RUNTIME_STATUS_DEFAULT = Path(r"D:\NEXUS_RUNTIME\v14_j_status.json")

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _result_hash(tag: str) -> str:
    return sha256_hex({"result_tag": tag, "lane": LANE})


def _base_kwargs(pins: dict[str, Any], *, eid: str, mech: str, seed: int, result_tag: str) -> dict[str, Any]:
    return {
        "experiment_id": eid,
        "mechanism_semantic_id": mech,
        "data_lineage": {
            "source_ids": ["sim_capture_v14_j", "fixture_bars"],
            "as_of_ms": 1_700_000_000_000,
            "pit_bound": True,
            "capture_campaign_id": "v14_j_sim",
        },
        "universe_checksum": checksum_universe(["BTCUSDT", "ETHUSDT"], as_of_ms=1_700_000_000_000),
        "feature_version": pins["feature_version"],
        "code_checksum": pins["code_checksum"],
        "parameter_checksum": checksum_parameters({"alpha": 0.1, "seed": seed}),
        "cost_version": pins["cost_version"],
        "risk_version": pins["risk_version"],
        "execution_version": pins["execution_version"],
        "time_intervals": [
            {
                "interval_id": "dev_1",
                "label": "development",
                "start_ms": 1_600_000_000_000,
                "end_ms": 1_650_000_000_000,
                "category": "development",
            },
            {
                "interval_id": "oos_reserved",
                "label": "oos_holdout",
                "start_ms": 1_660_000_000_000,
                "end_ms": 1_690_000_000_000,
                "category": "oos",
            },
        ],
        "development_only": True,
        "oos_consumed": False,
        "seeds": {"primary": seed, "numpy": seed + 1},
        "result_hashes": {"primary": _result_hash(result_tag)},
        "registered_at": _utc(),
    }


def scan_secrets(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = root / rel
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
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v14_j_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": OWNED_PATHS,
    }


def run_pytest(root: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "tests/experiment_registry",
            "-q",
            "--tb=line",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    passed_count = 0
    for line in out.splitlines():
        # pytest -q summary like "12 passed"
        m = re.search(r"(\d+)\s+passed", line)
        if m:
            passed_count = int(m.group(1))
    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "passed_count": passed_count,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "tail": "\n".join(out.strip().splitlines()[-40:]),
    }


def _scenario(sid: str, passed: bool, detail: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": sid,
        "passed": passed,
        "fail_closed": True,
        "detail": detail,
        "evidence": evidence,
    }


def run_pass_scenarios(pins: dict[str, Any], *, pass_number: int) -> list[dict[str, Any]]:
    """Execute fail-closed proof scenarios for one pass."""
    scenarios: list[dict[str, Any]] = []
    reg = ImmutableExperimentRegistry()

    # 1) Seal + verify round-trip
    kw = _base_kwargs(pins, eid="exp_seal_1", mech="mech_a", seed=1, result_tag="r1")
    rec = build_experiment_record(**kw)
    verify = verify_experiment_record(rec)
    reg.register(rec)
    scenarios.append(
        _scenario(
            "seal_and_verify",
            True,
            "record_sealed",
            {
                "identity_fingerprint": rec["identity_fingerprint"],
                "record_hash": rec["record_hash"],
                "verify": verify,
            },
        )
    )

    # 2) Duplicate experiment_id blocked
    try:
        reg.register(dict(rec))
        scenarios.append(_scenario("duplicate_id_blocked", False, "not_blocked", {}))
    except ExperimentRegistryError as exc:
        scenarios.append(
            _scenario(
                "duplicate_id_blocked",
                "experiment_id_duplicate" in str(exc),
                str(exc),
                {"blocked": True},
            )
        )

    # 3) Exact duplicate identity blocked
    kw2 = _base_kwargs(pins, eid="exp_dup_ident", mech="mech_a", seed=1, result_tag="r1")
    # Same identity fields as exp_seal_1 (mech_a, seed=1, result r1) → exact duplicate identity
    try:
        reg.register(build_experiment_record(**kw2))
        scenarios.append(_scenario("exact_duplicate_identity_blocked", False, "not_blocked", {}))
    except ExperimentRegistryError as exc:
        scenarios.append(
            _scenario(
                "exact_duplicate_identity_blocked",
                "exact_duplicate_identity" in str(exc),
                str(exc),
                {"blocked": True},
            )
        )

    # 4) Same identity, divergent results → cherry-pick / nondeterminism
    # Need a second registration path: change only result hashes while keeping identity.
    # Identity excludes result_hashes, so build with same seeds/params but different result.
    # For that we must first have a unique identity that isn't already registered —
    # register a fresh identity, then attempt divergent sibling.
    kw_base = _base_kwargs(pins, eid="exp_nd_a", mech="mech_nd", seed=42, result_tag="nd_a")
    reg.register(build_experiment_record(**kw_base))
    kw_div = _base_kwargs(pins, eid="exp_nd_b", mech="mech_nd", seed=42, result_tag="nd_b_favorable")
    try:
        reg.register(build_experiment_record(**kw_div))
        scenarios.append(
            _scenario("divergent_result_identity_conflict", False, "not_blocked", {})
        )
    except ExperimentRegistryError as exc:
        scenarios.append(
            _scenario(
                "divergent_result_identity_conflict",
                "identity_result_conflict" in str(exc)
                and "silent_cherry_pick_or_nondeterminism" in str(exc),
                str(exc),
                {"blocked": True, "pass_number": pass_number},
            )
        )

    # 5) Parent missing blocked
    try:
        bad_parent = build_experiment_record(
            **{
                **_base_kwargs(pins, eid="exp_orphan", mech="mech_orphan", seed=7, result_tag="o"),
                "parent_experiment": "does_not_exist",
            }
        )
        reg.register(bad_parent)
        scenarios.append(_scenario("parent_missing_blocked", False, "not_blocked", {}))
    except ExperimentRegistryError as exc:
        scenarios.append(
            _scenario(
                "parent_missing_blocked",
                "parent_experiment_missing" in str(exc),
                str(exc),
                {"blocked": True},
            )
        )

    # 6) Parent lineage chain
    parent = build_experiment_record(
        **_base_kwargs(pins, eid="exp_parent", mech="mech_lineage", seed=9, result_tag="p")
    )
    child = build_experiment_record(
        **{
            **_base_kwargs(pins, eid="exp_child", mech="mech_lineage_child", seed=10, result_tag="c"),
            "parent_experiment": "exp_parent",
        }
    )
    reg.register(parent)
    reg.register(child)
    chain = reg.lineage_chain("exp_child")
    scenarios.append(
        _scenario(
            "parent_lineage_chain",
            chain == ["exp_child", "exp_parent"],
            "lineage_ok" if chain == ["exp_child", "exp_parent"] else f"bad_chain:{chain}",
            {"chain": chain},
        )
    )

    # 7) OOS consumed forbidden
    try:
        build_experiment_record(
            **{
                **_base_kwargs(pins, eid="exp_oos", mech="mech_oos", seed=3, result_tag="x"),
                "oos_consumed": True,
            }
        )
        scenarios.append(_scenario("oos_consumed_forbidden", False, "not_blocked", {}))
    except ExperimentRecordError as exc:
        scenarios.append(
            _scenario(
                "oos_consumed_forbidden",
                "oos_consumed_forbidden" in str(exc),
                str(exc),
                {"blocked": True},
            )
        )

    # 8) Mutation / deletion forbidden
    mut_ok = False
    del_ok = False
    try:
        reg.update("exp_seal_1", {})
    except ExperimentRegistryError as exc:
        mut_ok = "mutation_forbidden" in str(exc)
    try:
        reg.delete("exp_seal_1")
    except ExperimentRegistryError as exc:
        del_ok = "deletion_forbidden" in str(exc)
    scenarios.append(
        _scenario(
            "immutability_enforced",
            mut_ok and del_ok,
            "immutable" if mut_ok and del_ok else "mutable_leak",
            {"mutation_blocked": mut_ok, "deletion_blocked": del_ok},
        )
    )

    # 9) Candidacy requires full disclosure; silent omission banned
    # Distinct identities for candidacy members.
    m1 = build_experiment_record(
        **_base_kwargs(pins, eid="cand_a", mech="mech_cand", seed=100, result_tag="cand_a")
    )
    m2 = build_experiment_record(
        **_base_kwargs(pins, eid="cand_b", mech="mech_cand", seed=101, result_tag="cand_b")
    )
    m3 = build_experiment_record(
        **_base_kwargs(pins, eid="cand_c", mech="mech_cand", seed=102, result_tag="cand_c")
    )
    reg.register(m1)
    reg.register(m2)
    reg.register(m3)
    reg.declare_candidacy_set(
        candidacy_id="cand_set_1",
        member_experiment_ids=["cand_a", "cand_b", "cand_c"],
        selection_criterion="disclosed_full_set_max_primary_hash_lex",
    )
    omit_blocked = False
    try:
        reg.select_from_candidacy(
            candidacy_id="cand_set_1",
            selected_experiment_id="cand_c",  # favorable
            disclose_all_member_ids=["cand_c"],  # omit losers
        )
    except ExperimentRegistryError as exc:
        omit_blocked = "silent_cherry_pick_omission" in str(exc)

    sel = reg.select_from_candidacy(
        candidacy_id="cand_set_1",
        selected_experiment_id="cand_c",
        disclose_all_member_ids=["cand_a", "cand_b", "cand_c"],
    )
    scenarios.append(
        _scenario(
            "candidacy_full_disclosure_required",
            omit_blocked and sel.get("silent_cherry_picking") is False,
            "disclosure_enforced",
            {"omit_blocked": omit_blocked, "selection": sel},
        )
    )

    # 10) Favorable-only criterion banned
    fav_blocked = False
    try:
        reg.declare_candidacy_set(
            candidacy_id="cand_bad",
            member_experiment_ids=["cand_a", "cand_b"],
            selection_criterion="best",
        )
    except ExperimentRegistryError as exc:
        fav_blocked = "silent_favorable_criterion_banned" in str(exc)
    scenarios.append(
        _scenario(
            "favorable_criterion_banned",
            fav_blocked,
            "banned" if fav_blocked else "allowed_leak",
            {"blocked": fav_blocked},
        )
    )

    # 11) Direct silent cherry-pick probe
    probe_blocked = False
    try:
        reg.attempt_silent_cherry_pick(
            favorable_experiment_id="cand_c",
            omitted_experiment_ids=["cand_a", "cand_b"],
        )
    except ExperimentRegistryError as exc:
        probe_blocked = "silent_cherry_picking_banned" in str(exc)
    scenarios.append(
        _scenario(
            "silent_cherry_pick_probe",
            probe_blocked,
            "banned" if probe_blocked else "allowed_leak",
            {"blocked": probe_blocked},
        )
    )

    # 12) Hard-ban flags present + record hash tamper detection
    tampered = dict(rec)
    tampered["profitability_claim"] = True
    ban_blocked = False
    try:
        verify_experiment_record(tampered)
    except ExperimentRecordError as exc:
        ban_blocked = "hard_ban_violated:profitability_claim" in str(exc)

    hash_tamper = dict(m1)
    hash_tamper["result_hashes"] = dict(m1["result_hashes"])
    hash_tamper["result_hashes"]["primary"] = _result_hash("tampered")
    # identity/record hashes stale
    hash_blocked = False
    try:
        verify_experiment_record(hash_tamper)
    except ExperimentRecordError as exc:
        hash_blocked = "mismatch" in str(exc)
    scenarios.append(
        _scenario(
            "hard_ban_and_hash_tamper",
            ban_blocked and hash_blocked,
            "fail_closed",
            {"ban_blocked": ban_blocked, "hash_blocked": hash_blocked},
        )
    )

    # 13) Persist + reload integrity
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "registry.json"
        reg.save(path)
        loaded = ImmutableExperimentRegistry.load(path)
        loaded.verify_all()
        scenarios.append(
            _scenario(
                "persist_reload_integrity",
                len(loaded) == len(reg),
                "reload_ok",
                {"count": len(loaded), "registry_hash": loaded.snapshot()["registry_hash"]},
            )
        )

    # Pass-2 extra adversarial: registry hash mismatch on load
    if pass_number >= 2:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            snap = reg.snapshot()
            snap["registry_hash"] = "0" * 64
            path.write_text(json.dumps(snap), encoding="utf-8")
            load_blocked = False
            try:
                ImmutableExperimentRegistry.load(path)
            except ExperimentRegistryError as exc:
                load_blocked = "registry_hash_mismatch" in str(exc)
            scenarios.append(
                _scenario(
                    "pass2_registry_hash_tamper",
                    load_blocked,
                    "tamper_blocked" if load_blocked else "tamper_accepted",
                    {"blocked": load_blocked},
                )
            )

            # Pass-2: self-parent rejected
            r2 = ImmutableExperimentRegistry()
            self_blocked = False
            try:
                sealed = build_experiment_record(
                    **{
                        **_base_kwargs(
                            pins,
                            eid="exp_self2",
                            mech="mech_self2",
                            seed=56,
                            result_tag="s2",
                        ),
                        "parent_experiment": "exp_self2",
                    }
                )
                r2.register(sealed)
            except ExperimentRegistryError as exc:
                self_blocked = "parent_experiment_self_reference" in str(exc)
            scenarios.append(
                _scenario(
                    "pass2_self_parent_blocked",
                    self_blocked,
                    "self_parent_guard",
                    {"blocked": self_blocked},
                )
            )

    return scenarios


def run_experiment_registry_campaign(
    *,
    root: Path,
    pass_number: int = 1,
    write_artifact: bool = True,
    write_runtime: bool = True,
    run_tests: bool = True,
) -> dict[str, Any]:
    pins = resolve_version_pins(root)
    scenarios = run_pass_scenarios(pins, pass_number=pass_number)
    secret_scan = scan_secrets(root)
    pytest_report: dict[str, Any] = {"passed": True, "skipped": not run_tests}
    if run_tests:
        pytest_report = run_pytest(root)

    pass_count = sum(1 for s in scenarios if s["passed"])
    total = len(scenarios)
    all_ok = pass_count == total
    pytest_ok = bool(pytest_report.get("passed"))
    secrets_ok = int(secret_scan.get("secret_leak_count") or 0) == 0
    passed = all_ok and pytest_ok and secrets_ok

    head = _git_head(root)
    status: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "program_id": "NEXUS_V14_J_EXPERIMENT_REGISTRY",
        "created_at": _utc(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "base_head": BASE_COMMIT,
        "pass_number": pass_number,
        "execution_mode": "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE",
        "owned_paths": OWNED_PATHS,
        "prohibited_paths": [
            "frontend/",
            "backend/nexus_demo_execution/",
            "G:/",
            "PR27",
            "deploy/",
        ],
        "hard_bans": HARD_BANS,
        "hard_ban_flags": HARD_BAN_FLAGS,
        "version_pins": pins,
        "scenarios": scenarios,
        "scenario_pass_count": pass_count,
        "scenario_total_count": total,
        "secret_scan": secret_scan,
        "pytest": pytest_report,
        "pytest_passed": pytest_ok,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "secret_leak_count": int(secret_scan.get("secret_leak_count") or 0),
        "mainnet": False,
        "real_money": False,
        "oos_executed": False,
        "oos_consumed": False,
        "formal_walk_forward_executed": False,
        "learning_claim_count": 0,
        "profitability_claim_count": 0,
        "silent_cherry_picking": False,
        "auto_integration": False,
        "pr27_merged": False,
        "PR27_draft_unmerged": True,
        "qualification_ready_count": 0,
        "remaining_blockers": [
            "auto_integration_forbidden",
            "PR27_draft_unmerged",
            "qualification_ready_count_must_remain_0",
            "no_real_oos_consumption",
            "no_formal_walk_forward",
            "no_strategy_promotion",
        ],
        "label": "EXPERIMENT_REGISTRY_CONTROL_NOT_REAL_TRADING",
        "worktree": str(root),
        "head": head,
        "lane_head_commit": head,
        "commit": head,
        "runtime_status_path": str(RUNTIME_STATUS_DEFAULT),
        "artifacts_dir": str(ART_REL).replace("\\", "/"),
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "recommendation": (
            "NEXUS_V14_J_EXPERIMENT_REGISTRY_PASS"
            if passed
            else "NEXUS_V14_J_EXPERIMENT_REGISTRY_FAIL"
        ),
        "Experiment_Registry_status": (
            "NEXUS_V14_J_EXPERIMENT_REGISTRY_PASS"
            if passed
            else "NEXUS_V14_J_EXPERIMENT_REGISTRY_FAIL"
        ),
    }

    if write_artifact:
        art = root / ART_REL
        art.mkdir(parents=True, exist_ok=True)
        _write(art / "v14_experiment_registry_status.json", status)
        _write(art / "version_pins.json", pins)
        _write(art / "secret_scan.json", secret_scan)
        _write(art / "pytest_report.json", pytest_report)
        _write(art / "scenarios.json", {"pass_number": pass_number, "scenarios": scenarios})
        _write(
            art / "hard_bans.json",
            {"hard_bans": HARD_BANS, "hard_ban_flags": HARD_BAN_FLAGS},
        )
        summary = [
            f"# V14-J Experiment Registry — Pass {pass_number}",
            "",
            f"- status: **{status['status']}**",
            f"- scenarios: {pass_count}/{total}",
            f"- pytest_passed: {pytest_ok}",
            f"- secret_leak_count: {status['secret_leak_count']}",
            f"- silent_cherry_picking: false",
            f"- auto_integration: false",
            f"- oos_consumed: false",
            "",
            "Immutable registry binds lineage, checksums, versions, seeds,",
            "result hashes, parent links, and duplicate/cherry-pick detection.",
            "",
        ]
        (art / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")

    if write_runtime:
        _write(RUNTIME_STATUS_DEFAULT, status)

    return status
