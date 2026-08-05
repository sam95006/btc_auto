"""PUB2-J Pass 2 — adversarial: try to detect missing a11y/i18n gates."""

from __future__ import annotations

from pathlib import Path

from backend.nexus_public_a11y_i18n_perf.hard_bans import scan_hard_bans

REPO = Path(__file__).resolve().parents[2]


def test_a11y_css_has_required_tokens():
    css = (REPO / "frontend" / "src" / "styles" / "a11yPerf.css").read_text(encoding="utf-8")
    for token in (
        "--nx-touch-min: 44px",
        "prefers-reduced-motion",
        "prefers-contrast",
        "forced-colors",
        "nx-skip-link",
        ":focus-visible",
        "overflow-x: clip",
    ):
        assert token in css, token


def test_e2e_spec_requires_wcag22_and_375():
    spec = (REPO / "frontend" / "e2e" / "a11y-member.spec.ts").read_text(encoding="utf-8")
    assert "wcag22aa" in spec
    assert "375" in spec
    assert "reducedMotion" in spec or "prefers-reduced-motion" in spec


def test_no_color_contrast_disable_in_member_a11y_spec():
    """Adversarial: member a11y suite must not silently disable contrast."""
    spec = (REPO / "frontend" / "e2e" / "a11y-member.spec.ts").read_text(encoding="utf-8")
    assert "disableRules" not in spec


def test_hard_ban_pass2():
    result = scan_hard_bans(2)
    assert result["ok"], result


def test_flutter_default_locale_zh_tw():
    app = (REPO / "apps" / "nexus_public_mobile" / "lib" / "app.dart").read_text(encoding="utf-8")
    strings = (
        REPO / "apps" / "nexus_public_mobile" / "lib" / "core" / "l10n" / "app_strings.dart"
    ).read_text(encoding="utf-8")
    assert "AppStrings.defaultLocale" in app
    assert "Locale('zh', 'TW')" in strings
