"""NEXUS Workstream-B final UI closure (source-level).

Guards the two Personal Plans UI fixes:
  1. The Personal comparison table uses canonical Free/Starter/Pro/Advanced columns
     sourced from the backend catalog capability matrix — not legacy hard-coded
     tier labels, and never an Enterprise column.
  2. The Enterprise Contact-Sales CTA never routes into Personal registration.
"""
from __future__ import annotations

from pathlib import Path

PAGE = Path("frontend") / "src" / "member_platform_v1" / "pages" / "PublicPages.tsx"


def _read() -> str:
    assert PAGE.exists(), f"missing {PAGE}"
    return PAGE.read_text(encoding="utf-8")


def test_comparison_table_is_backend_driven_canonical_columns():
    src = _read()
    # Columns + values are driven by the backend catalog (personalPlans + capability
    # matrix), so the mapping is explicit per plan and cannot silently shift.
    assert "personalPlans.map((p) =>" in src
    assert "caps[p.code]" in src
    # No legacy hard-coded comparison columns / old tier semantics.
    for legacy in ("<th>入門版</th>", "<th>進階版</th>", "<th>專業版</th>"):
        assert legacy not in src, legacy
    # Enterprise is never a Personal comparison column.
    assert "<th>企業版</th>" not in src


def test_enterprise_cta_does_not_route_to_personal_registration():
    src = _read()
    start = src.index("mpv1-enterprise-band")
    band = src[start:src.index("</section>", start)]
    # The Enterprise CTA must not route into the Personal registration flow.
    assert 'to="/register"' not in band, "Enterprise CTA must not route to Personal /register"
    # Honest, non-self-service state instead.
    assert "企業方案洽詢即將開放" in band
