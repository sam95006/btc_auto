"""Scan active source for four-fleet architecture violations."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

VIOLATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "BTC_FLEET": re.compile(r"BTC_FLEET"),
    "ETH_FLEET": re.compile(r"ETH_FLEET"),
    "SOL_FLEET": re.compile(r"SOL_FLEET"),
    "PEPE_FLEET": re.compile(r"PEPE_FLEET"),
    "four_fleet": re.compile(r"four[_-]fleet", re.I),
    "ShadowFleetCoordinator": re.compile(r"ShadowFleetCoordinator"),
    "fleet_id_required": re.compile(r"fleet_id\s*:\s*str(?!.*deprecated)"),
    "shadow_fleets_api": re.compile(r"/api/nexus/shadow/fleets"),
    "four_fleets_ui": re.compile(r"Four Fleets|四艦隊"),
}

FIXTURE_ALLOWLIST = frozenset(
    {
        "replay.py",
        "compat.py",
        "architecture_scan.py",
        "test_wave2_global_market_six_role.py",
        "__init__.py",
    }
)

BACKWARD_COMPAT_ALLOWLIST = frozenset({"compat.py", "contracts.py"})

UNIVERSE_HARDCODE = re.compile(
    r"\[\s*[\"']BTCUSDT[\"']\s*,\s*[\"']ETHUSDT[\"']\s*,\s*[\"']SOLUSDT[\"']\s*,\s*[\"']PEPEUSDT[\"']\s*\]"
)


@dataclass
class ScanFinding:
    path: str
    line: int
    pattern: str
    classification: str
    snippet: str = ""


@dataclass
class ArchitectureScanReport:
    root: str
    findings: list[ScanFinding] = field(default_factory=list)
    active_architecture_violation_count: int = 0

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "active_architecture_violation_count": self.active_architecture_violation_count,
            "findings": [
                {
                    "path": f.path,
                    "line": f.line,
                    "pattern": f.pattern,
                    "classification": f.classification,
                    "snippet": f.snippet,
                }
                for f in self.findings
            ],
        }


def scan_directory(
    root: Path,
    *,
    include_globs: Iterable[str] = ("**/*.py",),
    exclude_dirs: Iterable[str] = (".git", "__pycache__", "node_modules", "archives"),
) -> ArchitectureScanReport:
    report = ArchitectureScanReport(root=str(root))
    for glob in include_globs:
        for path in root.glob(glob):
            if any(part in exclude_dirs for part in path.parts):
                continue
            if path.name in FIXTURE_ALLOWLIST and "BENCHMARK" in path.read_text(encoding="utf-8", errors="ignore"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            rel = str(path.relative_to(root))
            for name, pattern in VIOLATION_PATTERNS.items():
                for i, line in enumerate(text.splitlines(), 1):
                    if not pattern.search(line):
                        continue
                    classification = _classify(rel, name, line)
                    finding = ScanFinding(rel, i, name, classification, line.strip()[:120])
                    report.findings.append(finding)
                    if classification == "ACTIVE_ARCHITECTURE_VIOLATION":
                        report.active_architecture_violation_count += 1
            if path.name not in FIXTURE_ALLOWLIST and UNIVERSE_HARDCODE.search(text):
                for i, line in enumerate(text.splitlines(), 1):
                    if UNIVERSE_HARDCODE.search(line):
                        report.findings.append(
                            ScanFinding(
                                rel,
                                i,
                                "hardcoded_four_symbol_universe",
                                "ACTIVE_ARCHITECTURE_VIOLATION",
                                line.strip()[:120],
                            )
                        )
                        report.active_architecture_violation_count += 1
    return report


def _classify(rel: str, pattern: str, line: str) -> str:
    if rel.replace("\\", "/").endswith("compat.py") or "strip_fleet_id" in line:
        return "BACKWARD_COMPATIBILITY"
    if "FIXTURE" in line or "BENCHMARK" in line or "NOT_AUTHORITATIVE" in line:
        return "FIXTURE_ONLY"
    if rel.startswith("docs/"):
        return "HISTORICAL_DOC"
    if pattern == "fleet_id_required" and "deprecated" in line.lower():
        return "BACKWARD_COMPATIBILITY"
    return "ACTIVE_ARCHITECTURE_VIOLATION"


def scan_nexus_global_shadow(package_root: Path | None = None) -> ArchitectureScanReport:
    if package_root is None:
        package_root = Path(__file__).resolve().parent
    return scan_directory(package_root)
