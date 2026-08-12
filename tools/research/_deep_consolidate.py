#!/usr/bin/env python3
"""Deep consolidation executor — docs/tools/alpha only; never mutates frozen H3 closure sources."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "readiness"
CLOSURE_PATH = OUT / "FROZEN_OOS_POLICY_CLOSURE.json"
H3E_EXPECT = "bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33"
H3D_EXPECT = "d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7"

ALWAYS_TOOLS = {
    "run_edge_research_v3.py",
    "run_edge_research_v2.py",
    "run_cohort_edge_research.py",
    "run_oos_risk_audit.py",
    "run_market_geometry_qualification.py",
    "__init__.py",
    "_build_frozen_closure.py",
    "_build_oos_preflight_cleanup.py",
    "_cleanup_unknown_pass2.py",
    "_scan_broken_readiness_refs.py",
    "_deep_consolidate.py",
    "performance_report.py",
}


def sha_obj(obj) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_policies() -> dict:
    out = {}
    for pid, expect in (
        ("H3E_OOS_POLICY_V1_FROZEN", H3E_EXPECT),
        ("H3D_OOS_POLICY_V1_FROZEN", H3D_EXPECT),
    ):
        p = OUT / "policies" / f"{pid}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        stored = d["policy_checksum"]
        recalc = sha_obj({k: v for k, v in d.items() if k != "policy_checksum"})
        out[pid] = {
            "stored": stored,
            "recalc": recalc,
            "expected": expect,
            "unchanged": stored == expect == recalc,
        }
    return out


def load_closure() -> set[str]:
    if CLOSURE_PATH.exists():
        return set(json.loads(CLOSURE_PATH.read_text(encoding="utf-8")).get("paths") or [])
    return set()


def tool_keep_dead() -> tuple[set[str], list[str]]:
    research = ROOT / "tools" / "research"
    name_to_path = {p.name: p for p in research.glob("*.py")}
    blob = ""
    for base in ["tests", ".github", "backend", "tools/ci"]:
        p = ROOT / base
        if not p.exists():
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.suffix.lower() in {".py", ".yml", ".yaml"}:
                try:
                    blob += f.read_text(encoding="utf-8", errors="ignore") + "\n"
                except OSError:
                    pass

    def local_imports(path: Path) -> set[str]:
        try:
            txt = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(txt)
        except Exception:
            return set()
        out: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                leaf = n.module.split(".")[-1] + ".py"
                if leaf in name_to_path:
                    out.add(leaf)
            if isinstance(n, ast.Import):
                for a in n.names:
                    leaf = a.name.split(".")[-1] + ".py"
                    if leaf in name_to_path:
                        out.add(leaf)
        for other in name_to_path:
            if other == path.name:
                continue
            stem = other[:-3]
            if f"import {stem}" in txt or f"from {stem} " in txt or f"tools.research.{stem}" in txt:
                out.add(other)
        return out

    seeds = set(ALWAYS_TOOLS)
    for name in name_to_path:
        if name in ALWAYS_TOOLS:
            continue
        if name in blob or f"tools/research/{name}" in blob:
            seeds.add(name)
    keep = set(seeds)
    changed = True
    while changed:
        changed = False
        for name in list(keep):
            if name not in name_to_path:
                continue
            for dep in local_imports(name_to_path[name]):
                if dep not in keep:
                    keep.add(dep)
                    changed = True
    dead = sorted(set(name_to_path) - keep)
    return keep, dead


def write_docs() -> list[str]:
    deleted: list[str] = []
    # Architecture / ops / research / UI SOT
    (ROOT / "docs" / "NEXUS_ARCHITECTURE.md").write_text(
        """# NEXUS Architecture (consolidated)

Current Demo Validation architecture focuses on:

- `backend/nexus_demo_execution/` bounded Demo session + offline qualification
- Cost Gate floors immutable (`MIN_NET_REWARD_RISK_RATIO=1.2`, `MIN_NET_REWARD_TO_COST=1.5`)
- Risk sizing `20U / 25x / ISOLATED / max notional 500U / max single loss 3U`
- Offline research pipeline culminating in Edge Research V3 / H3 event continuation
- Canonical readiness state under `docs/04_readiness/NEXUS_READINESS_SOT.md`

Historical Phase/Stage architecture narratives live in Git history only.
""",
        encoding="utf-8",
    )
    (ROOT / "docs" / "NEXUS_OPERATIONS.md").write_text(
        """# NEXUS Operations (consolidated)

Safety defaults:

- `EXCHANGE_WRITE=false`
- `MAINNET=false`
- `REAL_MONEY=false`
- Demo autonomous sessions require exact Founder phrases (6H/12H)

Current stage: OOS preflight frozen. Download/execute requires:

`APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1`

Do not redeploy Validation solely for repository hygiene.
Wallet delta remains a separate blocker (`UNKNOWN`).
""",
        encoding="utf-8",
    )
    (ROOT / "docs" / "NEXUS_RESEARCH_QUALIFICATION.md").write_text(
        """# NEXUS Research Qualification (consolidated)

Active qualification hierarchy:

- PRIMARY: H3E (`H3E_OOS_POLICY_V1_FROZEN`)
- CONFIRMATORY: H3D (`H3D_OOS_POLICY_V1_FROZEN`)
- EXPLORATORY: H3G (Replay only; cannot rescue failed H3E)

Excluded from new OOS: H1 / H2

Consumed:

- Research wave V2: `CONSUMED_NO_VALIDATED_COHORT`
- Failed holdout OOS: `OOS_REAL_MARKET_2026Q_FAILED_HOLDOUT_e186d13`

Gates unchanged. Maker fees are diagnostic-only.
""",
        encoding="utf-8",
    )
    ui_dir = ROOT / "docs" / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    (ui_dir / "NEXUS_UI_SOT.md").write_text(
        """# NEXUS UI Source of Truth (consolidated)

Supersedes MVP0–MVP22 incremental reports and Phase3–5 UI architecture drafts.

Current product boundary:

- Private operator surfaces vs public product boundary retained
- Sitemap / permission matrix / product spec historically defined under prior MVP docs (see Git history)
- Wave4 UI preservation matrix retained as CI fixture under `docs/04_readiness/`

Operational note: UI changes are out of scope for H3 OOS qualification.
""",
        encoding="utf-8",
    )

    # Delete superseded docs from the previous unknown set + related
    kill_prefixes = [
        ROOT / "docs" / "ui",
        ROOT / "docs" / "runbooks",
    ]
    keep_docs = {
        "docs/ui/NEXUS_UI_SOT.md",
        "docs/NEXUS_ARCHITECTURE.md",
        "docs/NEXUS_OPERATIONS.md",
        "docs/NEXUS_RESEARCH_QUALIFICATION.md",
        "docs/04_readiness/NEXUS_READINESS_SOT.md",
        "docs/04_readiness/README.md",
        "docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md",
        "docs/04_readiness/NEXUS_WAVE4_DATAHUNTERX_FEATURE_AUDIT.json",
        "docs/04_readiness/NEXUS_WAVE4_UI_FEATURE_PRESERVATION_MATRIX.json",
    }
    # also remove root superseded guides/plans
    for rel in [
        "docs/NEXUS_CURRENT_STATE.md",
        "docs/NEXUS_GUIDE.zh-TW.md",
        "docs/NEXUS_PHASE63_CONTROLLED_PAPER_ACTIVATION.md",
        "docs/research_stage3_bybit_demo_learning_runner_plan.md",
        "docs/research_stage3_phase_c_controlled_demo_order_plan.md",
        "docs/stage4_ai_decision_layer_plan.md",
        "docs/runbooks/STAGE_4_18_P2H_OPERATOR_HOLD_RUNBOOK.md",
    ]:
        p = ROOT / rel
        if p.exists() and rel not in keep_docs:
            deleted.append({"path": rel, "size": p.stat().st_size, "classification": "DOCUMENTATION_SUPERSEDED"})
            p.unlink()

    for p in (ROOT / "docs" / "ui").glob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in keep_docs:
            continue
        deleted.append({"path": rel, "size": p.stat().st_size, "classification": "DOCUMENTATION_SUPERSEDED"})
        p.unlink()

    return deleted


def consolidate_external_alpha() -> list[dict]:
    deleted: list[dict] = []
    src = ROOT / "data" / "external_alpha" / "reports"
    if not src.exists():
        return deleted
    dest = OUT / "immutable" / "external_alpha_baseline"
    dest.mkdir(parents=True, exist_ok=True)
    entries = []
    for p in sorted(src.glob("*.json")):
        checksum = sha_file(p)
        entries.append(
            {
                "report_type": p.stem,
                "source_path": p.relative_to(ROOT).as_posix(),
                "source_commit": "c6ddcafdecc10f166f6043e5baf08c98912561ca",
                "source_period": "stage3_legacy",
                "checksum": checksum,
                "current_status": "SUPERSEDED_SNAPSHOT",
                "retention_reason": "historical_stage3_readiness_fact_only",
                "replacement_path": "artifacts/readiness/immutable/external_alpha_baseline/external_alpha_manifest.json",
            }
        )
        # keep checksum facts only — delete raw after manifest
        deleted.append({"path": p.relative_to(ROOT).as_posix(), "size": p.stat().st_size, "classification": "GENERATED_OUTPUT"})
        p.unlink()
    (dest / "external_alpha_manifest.json").write_text(json.dumps({"entries": entries}, indent=2) + "\n", encoding="utf-8")
    return deleted


def delete_dead_tools(dead: list[str], closure: set[str]) -> list[dict]:
    deleted: list[dict] = []
    for name in dead:
        rel = f"tools/research/{name}"
        if rel in closure:
            continue
        p = ROOT / rel
        if not p.exists():
            continue
        deleted.append({"path": rel, "size": p.stat().st_size, "classification": "DEAD_CODE_CONFIRMED"})
        p.unlink()
    return deleted


def count_files() -> tuple[int, int]:
    files = [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return len(files), sum(p.stat().st_size for p in files)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pol_before = verify_policies()
    if not all(v["unchanged"] for v in pol_before.values()):
        raise SystemExit("ABORT_OOS_PREPARATION FROZEN_POLICY_MUTATED before consolidation")

    closure = load_closure()
    files_before, bytes_before = count_files()
    keep, dead = tool_keep_dead()

    deleted: list[dict] = []
    deleted.extend(write_docs())
    deleted.extend(consolidate_external_alpha())
    deleted.extend(delete_dead_tools(dead, closure))

    # prune empty dirs under docs/ui tools leftovers
    for d in sorted((ROOT / "docs").rglob("*"), reverse=True):
        if d.is_dir():
            try:
                next(d.iterdir())
            except StopIteration:
                try:
                    d.rmdir()
                except OSError:
                    pass
            except OSError:
                pass

    pol_after = verify_policies()
    if not all(v["unchanged"] for v in pol_after.values()):
        raise SystemExit("ABORT_OOS_PREPARATION classification=FROZEN_POLICY_MUTATED")

    files_after, bytes_after = count_files()
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files_before": files_before,
        "files_after": files_after,
        "files_removed": len(deleted),
        "bytes_removed": sum(int(x.get("size") or 0) for x in deleted),
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
        "tools_kept": sorted(keep),
        "tools_dead_removed": [x["path"] for x in deleted if x["path"].startswith("tools/research/")],
        "policy_before": pol_before,
        "policy_after": pol_after,
        "h3e_policy_unchanged": pol_after["H3E_OOS_POLICY_V1_FROZEN"]["unchanged"],
        "h3d_policy_unchanged": pol_after["H3D_OOS_POLICY_V1_FROZEN"]["unchanged"],
        "deleted": deleted,
    }
    (OUT / "deep_consolidation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "deleted"}, indent=2))


if __name__ == "__main__":
    main()
