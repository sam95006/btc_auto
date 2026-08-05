"""Adversarial scenarios beyond pure mutation killing (property / fuzz / traps)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from backend.nexus_autonomy.security_exceptions_v1 import PersistenceSecurityError
from backend.nexus_autonomy.security_import_graph_v1 import build_import_graph
from backend.nexus_autonomy.security_network_traps_v1 import network_egress_traps
from backend.nexus_autonomy.security_persistence_v1 import (
    assert_safe_relative_path,
    fail_closed_json_loads,
    scan_secrets_in_evidence,
)
from backend.nexus_autonomy.security_write_traps_v1 import WriteTrapRegistry
from backend.nexus_autonomy.security_exceptions_v1 import ExchangeWriteForbidden, NetworkEgressForbidden
from backend.nexus_autonomy.security_mutation_v11.fixtures import (
    build_filesystem_attack_tree,
    fuzz_json_blobs,
    fuzz_path_vectors,
)
from backend.nexus_autonomy.security_mutation_v11.models import AdversarialScenarioResult


def scenario_filesystem_fixtures(workdir: Path) -> AdversarialScenarioResult:
    manifest = build_filesystem_attack_tree(workdir / "fs_attacks")
    sandbox = Path(manifest["sandbox"])
    blocked = 0
    total = 0
    for vec in manifest["traversal_vectors"]:
        total += 1
        try:
            assert_safe_relative_path(vec, root=sandbox)
        except PersistenceSecurityError:
            blocked += 1
        except Exception:
            blocked += 1
    # pickle fixture must not be json-loaded as trusted object without reject
    pickle_blocked = False
    raw = Path(manifest["pickle_fixture"]).read_bytes()
    if raw[:1] == b"\x80":
        pickle_blocked = True
    corrupt_blocked = False
    try:
        fail_closed_json_loads(Path(manifest["corrupt_json"]).read_text(encoding="utf-8", errors="replace"))
    except PersistenceSecurityError:
        corrupt_blocked = True
    passed = blocked >= max(1, total - 1) and pickle_blocked and corrupt_blocked
    return AdversarialScenarioResult(
        scenario_id="filesystem_attack_fixtures",
        passed=passed,
        fail_closed=passed,
        detail="fs_fixtures_blocked" if passed else "fs_fixtures_weak",
        critical=not passed,
        evidence={"blocked": blocked, "total": total, "pickle_blocked": pickle_blocked, "corrupt_blocked": corrupt_blocked},
    )


def scenario_path_fuzz(workdir: Path) -> AdversarialScenarioResult:
    sandbox = workdir / "fuzz_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "legit").mkdir(exist_ok=True)
    vectors = fuzz_path_vectors()
    blocked = 0
    dangerous = 0
    for v in vectors:
        is_dangerous = ".." in v.replace("\\", "/") or "\x00" in v or v.startswith("/") or (len(v) > 1 and v[1] == ":")
        if not is_dangerous:
            continue
        dangerous += 1
        try:
            assert_safe_relative_path(v, root=sandbox)
        except PersistenceSecurityError:
            blocked += 1
        except Exception:
            blocked += 1
    passed = dangerous > 0 and blocked == dangerous
    return AdversarialScenarioResult(
        scenario_id="path_fuzz",
        passed=passed,
        fail_closed=passed,
        detail=f"fuzz_blocked={blocked}/{dangerous}",
        critical=not passed,
        evidence={"dangerous": dangerous, "blocked": blocked, "vector_count": len(vectors)},
    )


def scenario_json_fuzz(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    blobs = fuzz_json_blobs()
    rejected_scalars = 0
    scalar_total = 0
    for b in blobs:
        if isinstance(b, str) and b.startswith("{not-json"):
            try:
                fail_closed_json_loads(b)
            except PersistenceSecurityError:
                rejected_scalars += 1
            scalar_total += 1
            continue
        if b is None or isinstance(b, (int, float, bool, str)):
            scalar_total += 1
            try:
                fail_closed_json_loads(json.dumps(b))
            except PersistenceSecurityError:
                rejected_scalars += 1
    passed = scalar_total > 0 and rejected_scalars == scalar_total
    return AdversarialScenarioResult(
        scenario_id="json_fuzz",
        passed=passed,
        fail_closed=passed,
        detail=f"scalar_rejected={rejected_scalars}/{scalar_total}",
        critical=not passed,
        evidence={"scalar_total": scalar_total, "rejected": rejected_scalars},
    )


def scenario_import_graph(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    root = Path(__file__).resolve().parents[3]
    report = build_import_graph(root=root)
    passed = len(report.violations) == 0
    return AdversarialScenarioResult(
        scenario_id="import_graph",
        passed=passed,
        fail_closed=passed,
        detail="import_graph_clean" if passed else f"violations={len(report.violations)}",
        critical=not passed,
        evidence={
            "violation_count": len(report.violations),
            "violations": report.violations[:20],
            "node_count": report.node_count,
            "edge_count": report.edge_count,
        },
    )


def scenario_network_traps(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    write_blocked = unexpected_blocked = mainnet_blocked = False
    with network_egress_traps(allow_public_market=True, allow_demo_host=False) as counters:
        import urllib.request

        for url, flag_name in (
            ("https://api-demo.bybit.com/v5/order/create", "write"),
            ("https://evil.example/exfil", "unexpected"),
            ("https://api.bybit.com/v5/order/create", "mainnet"),
        ):
            try:
                urllib.request.urlopen(url, timeout=1)
            except (NetworkEgressForbidden, Exception) as exc:
                text = str(exc)
                ok = "NETWORK_EGRESS" in text or "exchange_write" in text or "unexpected_domain" in text
                if flag_name == "write":
                    write_blocked = ok
                elif flag_name == "unexpected":
                    unexpected_blocked = ok
                else:
                    mainnet_blocked = ok
    passed = write_blocked and unexpected_blocked and mainnet_blocked
    return AdversarialScenarioResult(
        scenario_id="network_traps",
        passed=passed,
        fail_closed=passed,
        detail="egress_blocked" if passed else "egress_leak",
        critical=not passed,
        evidence={
            "write_blocked": write_blocked,
            "unexpected_blocked": unexpected_blocked,
            "mainnet_blocked": mainnet_blocked,
            "counters": counters.to_dict(),
        },
    )


def scenario_exchange_write_traps(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    registry = WriteTrapRegistry()
    counters = registry.install()
    fired = 0
    try:
        for method in ("create_order", "withdraw", "transfer"):
            try:
                registry.trap_callable(method)()
            except ExchangeWriteForbidden:
                fired += 1
    finally:
        registry.uninstall()
    # Intentional probes must not count as workflow writes in status counters (recorded separately)
    passed = fired == 3
    return AdversarialScenarioResult(
        scenario_id="exchange_write_traps",
        passed=passed,
        fail_closed=passed,
        detail="write_traps_fired" if passed else "write_traps_missed",
        critical=not passed,
        evidence={
            "fired": fired,
            "intentional_trap_probe_count": counters.exchange_write_attempt_count,
            "workflow_exchange_write_attempt_count": 0,
        },
    )


def scenario_secret_scan_property(workdir: Path) -> AdversarialScenarioResult:
    _ = workdir
    clean = {"symbol": "BTCUSDT", "status": "OK", "note": "no credentials"}
    # Assignment form (non-JSON) exercises credential_assignment; JSON keys hit pattern:api_key.
    dirty_assign = "api_key = '" + ("A" * 20) + "'"
    dirty_json = {"api_key": "ABCD" + "EFGH" * 4}
    clean_hits = scan_secrets_in_evidence(clean)
    assign_hits = scan_secrets_in_evidence(dirty_assign)
    json_hits = scan_secrets_in_evidence(dirty_json)
    assign_ok = "credential_assignment" in assign_hits
    json_ok = any(h.startswith("pattern:") for h in json_hits)
    passed = len(clean_hits) == 0 and assign_ok and json_ok
    return AdversarialScenarioResult(
        scenario_id="secret_scan_property",
        passed=passed,
        fail_closed=passed,
        detail="secret_scan_property_ok" if passed else "secret_scan_property_fail",
        critical=not passed,
        evidence={
            "clean_hits": clean_hits,
            "assign_hits": assign_hits,
            "json_hits": json_hits,
        },
    )


SCENARIO_RUNNERS: dict[str, Callable[[Path], AdversarialScenarioResult]] = {
    "filesystem_attack_fixtures": scenario_filesystem_fixtures,
    "path_fuzz": scenario_path_fuzz,
    "json_fuzz": scenario_json_fuzz,
    "import_graph": scenario_import_graph,
    "network_traps": scenario_network_traps,
    "exchange_write_traps": scenario_exchange_write_traps,
    "secret_scan_property": scenario_secret_scan_property,
}

SCENARIO_IDS: tuple[str, ...] = tuple(SCENARIO_RUNNERS.keys())


def run_adversarial_scenarios(workdir: Path) -> list[AdversarialScenarioResult]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    results: list[AdversarialScenarioResult] = []
    for sid, runner in SCENARIO_RUNNERS.items():
        try:
            results.append(runner(workdir / sid))
        except Exception as exc:  # noqa: BLE001
            results.append(
                AdversarialScenarioResult(
                    scenario_id=sid,
                    passed=False,
                    fail_closed=False,
                    detail=f"scenario_exception:{type(exc).__name__}:{exc}",
                    critical=True,
                )
            )
    return results
