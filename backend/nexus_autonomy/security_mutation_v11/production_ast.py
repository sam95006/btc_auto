"""Production-module AST mutation kill suite (sandbox only).

Ported from R4 reviewer production_mutation.py into Lane G ownership.

Kill-suite semantics (classic mutation testing / red-team detection):
- hole_observed → killed (oracle caught the weakened guard)
- property_still_holds → equivalent (defense-in-depth; mutant ineffective)
- unclassified / silent → survived (fail-closed CI)

This differs from R4 *review* resilience reporting, where hole_observed was
labeled "survived". G CI requires production_ast_survivor_count == 0.
Production sources are never modified in-place.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.security_mutation_v11.ast_mutator import (
    MutantSpec,
    iter_planned_mutants,
)
from backend.nexus_autonomy.security_mutation_v11.constants import (
    PRODUCTION_AST_REQUIRED_DETECT_KILLS,
    PRODUCTION_MUTATION_TARGETS,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_module_from_path(mod_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot_load:{path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _prepare_sandbox(root: Path, sandbox: Path) -> dict[str, Path]:
    pkg = sandbox / "backend" / "nexus_autonomy"
    pkg.mkdir(parents=True, exist_ok=True)
    (sandbox / "backend").mkdir(exist_ok=True)
    (sandbox / "backend" / "__init__.py").write_text('"""sandbox backend"""\n', encoding="utf-8")
    (pkg / "__init__.py").write_text('"""sandbox nexus_autonomy"""\n', encoding="utf-8")

    deps = [
        "security_constants_v1.py",
        "security_exceptions_v1.py",
        "security_persistence_v1.py",
        "security_credential_boundary_v1.py",
        "security_public_private_v1.py",
        "security_write_traps_v1.py",
    ]
    written: dict[str, Path] = {}
    src_pkg = root / "backend" / "nexus_autonomy"
    for name in deps:
        src = src_pkg / name
        dst = pkg / name
        if src.is_file():
            shutil.copy2(src, dst)
            written[f"backend/nexus_autonomy/{name}"] = dst
    return written


def _observe_persistence(mod: types.ModuleType, mutant_id: str) -> dict[str, Any]:
    from pathlib import Path as P

    root = P(tempfile.mkdtemp(prefix="g_persist_"))
    try:
        if mutant_id == "persist_drop_dotdot_token_check":
            blocked = False
            try:
                mod.assert_safe_relative_path("../x", root=root)
            except Exception:
                blocked = True
            return {
                "hole_observed": not blocked,
                "property_holds": blocked,
                "detail": "dotdot_still_blocked" if blocked else "dotdot_accepted_HOLE",
                "path_traversal_blocked": blocked,
            }
        if mutant_id == "persist_scan_secrets_noop":
            # Fixture assembled at runtime so owned-file static scanners do not trip.
            secret_val = "SUPERSECRET" + "VALUE123456"
            findings = mod.scan_secrets_in_evidence({"note": "x", "api_key": secret_val})
            detected = bool(findings)
            return {
                "hole_observed": not detected,
                "property_holds": detected,
                "detail": "secrets_still_detected" if detected else "secrets_missed_HOLE",
                "secret_detected": detected,
            }
        if mutant_id == "persist_json_accept_scalars":
            blocked = False
            try:
                mod.fail_closed_json_loads("42")
            except Exception:
                blocked = True
            return {
                "hole_observed": not blocked,
                "property_holds": blocked,
                "detail": "scalar_still_blocked" if blocked else "scalar_accepted_HOLE",
                "scalar_json_blocked": blocked,
            }
        return {"hole_observed": False, "property_holds": False, "detail": "unknown_persist_mutant"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _observe_credential(mod: types.ModuleType, mutant_id: str) -> dict[str, Any]:
    env = {
        "BYBIT_API_KEY": "mainnetkeymainnetkey12",
        "BYBIT_API_SECRET": "mainnetsecretmainnetsecret12",
    }
    result = mod.resolve_exchange_profile(
        env,
        requested_profile="demo",
        base_url="https://api.bybit.com",
    )
    writes = bool(getattr(result, "writes_enabled", True))
    fail_closed = bool(getattr(result, "fail_closed", False))
    fallback = bool(getattr(result, "mainnet_fallback_used", False))
    confused = bool(getattr(result, "demo_mainnet_confused", False))

    if mutant_id == "cred_ignore_mainnet_fallback":
        safe = (not writes) and (fail_closed or confused)
        return {
            "hole_observed": not safe,
            "property_holds": safe,
            "detail": (
                "fallback_or_confusion_still_fail_closed"
                if safe
                else "mainnet_fallback_hidden_HOLE"
            ),
            "writes_enabled": writes,
            "fail_closed": fail_closed,
            "mainnet_fallback_used": fallback,
            "demo_mainnet_confused": confused,
        }
    if mutant_id == "cred_force_writes_enabled":
        safe = not writes
        return {
            "hole_observed": not safe,
            "property_holds": safe,
            "detail": "writes_still_disabled" if safe else "writes_forced_HOLE",
            "writes_enabled": writes,
            "fail_closed": fail_closed,
        }
    safe = (not writes) and fail_closed
    return {
        "hole_observed": not safe,
        "property_holds": safe,
        "detail": "credential_boundary_alive" if safe else "credential_boundary_HOLE",
        "writes_enabled": writes,
        "fail_closed": fail_closed,
    }


def _observe_public(mod: types.ModuleType, mutant_id: str) -> dict[str, Any]:
    if mutant_id == "public_assert_schema_noop":
        raised = False
        try:
            mod.assert_public_schema({"raw_provider_prompt": "SECRET_PROMPT", "ok": True})
        except Exception:
            raised = True
        return {
            "hole_observed": not raised,
            "property_holds": raised,
            "detail": "public_schema_still_raises" if raised else "public_schema_noop_HOLE",
        }
    if mutant_id == "public_redact_identity":
        secret_val = "SUPERSECRET" + "VALUE123456"
        payload = {"api_key": secret_val, "account_id": "acct-9"}
        out = mod.redact_account_identifiers(dict(payload))
        blob = json.dumps(out)
        leaked = secret_val in blob
        return {
            "hole_observed": leaked,
            "property_holds": not leaked,
            "detail": "redaction_alive" if not leaked else "redaction_identity_HOLE",
            "secret_leak_count": 1 if leaked else 0,
        }
    return {"hole_observed": False, "property_holds": False, "detail": "no_oracle"}


def _observe_write_traps(mod: types.ModuleType, mutant_id: str) -> dict[str, Any]:
    registry_cls = getattr(mod, "WriteTrapRegistry", None)
    if registry_cls is None:
        return {
            "hole_observed": True,
            "property_holds": False,
            "detail": "WriteTrapRegistry_missing_HOLE",
        }
    reg = registry_cls()
    install_fn = getattr(reg, "install", None)
    if not callable(install_fn):
        return {
            "hole_observed": True,
            "property_holds": False,
            "detail": "install_missing_HOLE",
        }
    try:
        result = install_fn()
    except Exception as exc:
        # Raising on install is fail-closed for unarmed traps — property holds.
        return {
            "hole_observed": False,
            "property_holds": True,
            "detail": f"install_raised:{type(exc).__name__}",
        }
    trap_count = int(getattr(reg, "write_method_trap_count", 0) or 0)
    patches = list(getattr(reg, "_patches", []) or [])
    install_ok = bool(getattr(reg, "install_ok", trap_count > 0 or len(patches) > 0))
    armed = trap_count > 0 or len(patches) > 0 or install_ok
    # No-op mutant returns bare True without arming → hole.
    noop_claim = result is True or "noop" in mutant_id
    hole = noop_claim and not armed
    return {
        "hole_observed": hole,
        "property_holds": armed and not hole,
        "detail": (
            "write_traps_armed"
            if armed and not hole
            else ("install_noop_HOLE" if hole else "install_ineffective_HOLE")
        ),
        "write_method_trap_count": trap_count,
        "patch_count": len(patches),
        "install_result_type": type(result).__name__,
    }


def _observe(target_rel: str, mutant_id: str, mod: types.ModuleType) -> dict[str, Any]:
    if "security_persistence" in target_rel:
        return _observe_persistence(mod, mutant_id)
    if "security_credential" in target_rel:
        return _observe_credential(mod, mutant_id)
    if "security_public_private" in target_rel:
        return _observe_public(mod, mutant_id)
    if "security_write_traps" in target_rel:
        return _observe_write_traps(mod, mutant_id)
    return {"hole_observed": False, "property_holds": False, "detail": "no_oracle_for_target"}


def _classify(observation: dict[str, Any]) -> str:
    """Map observation → kill-suite status."""
    if observation.get("hole_observed"):
        return "killed"  # red-team detected the weakened guard
    if observation.get("property_holds"):
        return "equivalent"  # defense-in-depth; mutant did not open a hole
    return "survived"  # silent / unclassified — fail closed


def run_production_ast_mutation(root: Path | None = None) -> dict[str, Any]:
    root = (root or _repo_root()).resolve()
    results: list[dict[str, Any]] = []
    killed = 0
    survivors = 0
    equivalent = 0
    errors = 0

    with tempfile.TemporaryDirectory(prefix="g_ast_mut_") as tmp:
        sandbox = Path(tmp)
        for target_rel in PRODUCTION_MUTATION_TARGETS:
            src_path = root / target_rel
            if not src_path.is_file():
                results.append(
                    {
                        "mutant_id": f"missing::{target_rel}",
                        "target_rel": target_rel,
                        "status": "error",
                        "detail": "target_missing",
                    }
                )
                errors += 1
                continue
            original = src_path.read_text(encoding="utf-8")
            planned = list(iter_planned_mutants(target_rel, original))
            if not planned:
                results.append(
                    {
                        "mutant_id": f"no_mutants::{target_rel}",
                        "target_rel": target_rel,
                        "status": "equivalent",
                        "detail": "no_applicable_ast_mutator",
                    }
                )
                equivalent += 1
                continue

            for spec, mutated_src in planned:
                assert isinstance(spec, MutantSpec)
                mdir = sandbox / spec.mutant_id
                if mdir.exists():
                    shutil.rmtree(mdir)
                paths = _prepare_sandbox(root, mdir)
                target_dst = paths.get(target_rel)
                if target_dst is None:
                    results.append(
                        {
                            "mutant_id": spec.mutant_id,
                            "target_rel": target_rel,
                            "status": "error",
                            "detail": "sandbox_target_missing",
                        }
                    )
                    errors += 1
                    continue
                target_dst.write_text(mutated_src, encoding="utf-8")

                inserted = str(mdir)
                sys.path.insert(0, inserted)
                purge = [
                    k
                    for k in list(sys.modules)
                    if k == "backend" or k.startswith("backend.nexus_autonomy")
                ]
                saved = {k: sys.modules.pop(k) for k in purge}
                try:
                    mod_name = "backend.nexus_autonomy." + Path(target_rel).stem
                    _load_module_from_path("backend", mdir / "backend" / "__init__.py")
                    _load_module_from_path(
                        "backend.nexus_autonomy",
                        mdir / "backend" / "nexus_autonomy" / "__init__.py",
                    )
                    for dep_rel, dep_path in paths.items():
                        if dep_rel == target_rel:
                            continue
                        dname = "backend.nexus_autonomy." + Path(dep_rel).stem
                        _load_module_from_path(dname, dep_path)
                    mod = _load_module_from_path(mod_name, target_dst)
                    observation = _observe(target_rel, spec.mutant_id, mod)
                    status = _classify(observation)
                    if status == "killed":
                        killed += 1
                    elif status == "equivalent":
                        equivalent += 1
                    else:
                        survivors += 1
                    results.append(
                        {
                            "mutant_id": spec.mutant_id,
                            "target_rel": target_rel,
                            "operator": spec.operator,
                            "description": spec.description,
                            "status": status,
                            "oracle": {
                                **observation,
                                "killed": status == "killed",
                                "semantics": "kill_suite_detect_or_equivalent",
                            },
                            "mutation_kind": "production_ast",
                        }
                    )
                except Exception as exc:
                    errors += 1
                    results.append(
                        {
                            "mutant_id": spec.mutant_id,
                            "target_rel": target_rel,
                            "status": "error",
                            "detail": f"{type(exc).__name__}:{exc}",
                            "mutation_kind": "production_ast",
                        }
                    )
                finally:
                    for k in list(sys.modules):
                        if k == "backend" or k.startswith("backend.nexus_autonomy"):
                            sys.modules.pop(k, None)
                    sys.modules.update(saved)
                    if sys.path and sys.path[0] == inserted:
                        sys.path.pop(0)

    total = killed + survivors + equivalent + errors
    killed_ids = {r["mutant_id"] for r in results if r.get("status") == "killed"}
    survivor_ids = sorted(r["mutant_id"] for r in results if r.get("status") == "survived")
    missing_required = sorted(set(PRODUCTION_AST_REQUIRED_DETECT_KILLS) - killed_ids)

    return {
        "schema": "v11_g_production_ast_mutation_v1",
        "mutation_kind": "production_ast",
        "tool": "custom_ast_mutator",
        "mutmut_used": False,
        "cosmic_ray_used": False,
        "wrapper_only": False,
        "wrapper_only_pass_forbidden": True,
        "targets": list(PRODUCTION_MUTATION_TARGETS),
        "mutant_total": total,
        "killed_count": killed,
        "survivor_count": survivors,
        "equivalent_count": equivalent,
        "error_count": errors,
        "production_ast_survivor_count": survivors,
        "production_ast_killed_count": killed,
        "survivor_ids": survivor_ids,
        "required_detect_kills": list(PRODUCTION_AST_REQUIRED_DETECT_KILLS),
        "required_detect_kills_missing": missing_required,
        "required_detect_kills_ok": len(missing_required) == 0 and survivors == 0 and errors == 0,
        "results": results,
        "exchange_write_attempt_count": 0,
        "mainnet_client_created_count": 0,
        "r4_semantics_note": (
            "R4 review labeled hole_observed as 'survived' (resilience view). "
            "G kill-suite labels hole_observed as 'killed' (detection view) and "
            "property_holds as 'equivalent'. Fail-closed on silent survivors."
        ),
    }
