"""Static security scans for Wave 5 public data boundary."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent

FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_order_endpoint", re.compile(r"/v5/order", re.I)),
    ("private_position_endpoint", re.compile(r"/v5/position", re.I)),
    ("private_account_endpoint", re.compile(r"/v5/account", re.I)),
    ("private_asset_endpoint", re.compile(r"/v5/asset", re.I)),
    ("auth_header_literal", re.compile(r"x-bapi-(api-key|sign|timestamp)", re.I)),
    ("write_method_bybit", re.compile(r'\.(post|put|patch|delete)\s*\(\s*[^)]*bybit', re.I)),
    ("api_secret_literal", re.compile(r"(api[_-]?secret|private[_-]?key)\s*=", re.I)),
]

ALLOWED_EXCEPTION_FILES = frozenset(
    {
        "constitution.py",
        "security_scan.py",
    }
)


@dataclass
class ScanFinding:
    file: str
    line: int
    pattern: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "pattern": self.pattern,
            "snippet": self.snippet,
        }


@dataclass
class SecurityScanReport:
    scanned_files: int = 0
    findings: list[ScanFinding] = field(default_factory=list)

    @property
    def violation_count(self) -> int:
        return len(self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_files": self.scanned_files,
            "violation_count": self.violation_count,
            "findings": [f.to_dict() for f in self.findings],
            "passed": self.violation_count == 0,
        }


def scan_file(path: Path) -> list[ScanFinding]:
    if path.name in ALLOWED_EXCEPTION_FILES:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    findings: list[ScanFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(line):
                findings.append(
                    ScanFinding(
                        file=str(path.relative_to(PACKAGE_ROOT.parent.parent)),
                        line=lineno,
                        pattern=name,
                        snippet=stripped[:120],
                    )
                )
    return findings


def scan_package(root: Path | None = None) -> SecurityScanReport:
    base = root or PACKAGE_ROOT
    report = SecurityScanReport()
    for path in sorted(base.rglob("*.py")):
        report.scanned_files += 1
        report.findings.extend(scan_file(path))
    return report


def assert_package_clean(root: Path | None = None) -> SecurityScanReport:
    report = scan_package(root)
    if report.violation_count:
        detail = "; ".join(f"{f.file}:{f.line}:{f.pattern}" for f in report.findings[:5])
        raise AssertionError(f"security_scan_failed:{detail}")
    return report
