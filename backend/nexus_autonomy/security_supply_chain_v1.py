"""Low-risk supply-chain / CI posture audit (findings only; no mass upgrades)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SupplyFinding:
    severity: str  # critical|high|medium|low
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "detail": self.detail}


@dataclass
class SupplyChainReport:
    findings: list[SupplyFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "supply_chain_finding_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "critical_count": sum(1 for f in self.findings if f.severity == "critical"),
            "high_count": sum(1 for f in self.findings if f.severity == "high"),
            "medium_count": sum(1 for f in self.findings if f.severity == "medium"),
            "low_count": sum(1 for f in self.findings if f.severity == "low"),
        }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def audit_supply_chain(root: Path | None = None) -> SupplyChainReport:
    base = root or _repo_root()
    report = SupplyChainReport()
    workflows = list((base / ".github" / "workflows").glob("*.yml")) + list(
        (base / ".github" / "workflows").glob("*.yaml")
    )
    for wf in workflows:
        try:
            text = wf.read_text(encoding="utf-8")
        except OSError:
            continue
        # Unpinned third-party actions (mutable tags)
        for m in re.finditer(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([A-Za-z0-9._/-]+)", text):
            action, ref = m.group(1), m.group(2)
            if ref in {"main", "master", "latest"} or (
                not re.fullmatch(r"[0-9a-f]{40}", ref) and not ref.startswith("v")
            ):
                # allow v1 style tags as medium; main/master as high
                sev = "high" if ref in {"main", "master", "latest"} else "low"
                report.findings.append(
                    SupplyFinding(
                        severity=sev,
                        code="mutable_or_unpinned_action",
                        detail=f"{wf.name}:{action}@{ref}",
                    )
                )
        if "pull_request_target" in text and "checkout" in text.lower():
            report.findings.append(
                SupplyFinding(
                    severity="high",
                    code="pull_request_target_checkout",
                    detail=wf.name,
                )
            )
        if re.search(r"curl\s+[^\n]*\|\s*(ba)?sh", text):
            report.findings.append(
                SupplyFinding(severity="high", code="pipe_curl_to_shell", detail=wf.name)
            )
        if "secrets." in text and "echo" in text.lower():
            # heuristic only
            if re.search(r"echo\s+.*\$\{\{\s*secrets\.", text):
                report.findings.append(
                    SupplyFinding(severity="critical", code="secret_echo_in_workflow", detail=wf.name)
                )

    req = base / "requirements.txt"
    if req.exists():
        try:
            lines = req.read_text(encoding="utf-8").splitlines()
            unpinned = [
                ln.strip()
                for ln in lines
                if ln.strip() and not ln.strip().startswith("#") and "==" not in ln and "@" not in ln
            ]
            for pkg in unpinned[:10]:
                report.findings.append(
                    SupplyFinding(severity="low", code="unpinned_python_dep", detail=pkg)
                )
        except OSError:
            pass

    return report
