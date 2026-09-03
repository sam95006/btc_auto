"""Personal auth-recovery UX hotfix (source-level).

Guards: (1) auth inputs have an explicit, theme-correct readable contract so text
is never white-on-white; (2) the forgot-password UI is truthful about whether a
reset email can actually be delivered.
"""
from __future__ import annotations

from pathlib import Path

CSS = Path("frontend/src/member_platform_v1/styles/memberPlatformV1.css")
PUBLIC = Path("frontend/src/member_platform_v1/pages/PublicPages.tsx")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def _input_block(src: str) -> str:
    start = src.index(".mpv1-input input {")
    return src[start:start + 900]


def test_auth_input_has_explicit_readable_contract():
    src = _css()
    block = _input_block(src)
    assert "color: var(--mp-text)" in block
    assert "caret-color: var(--mp-accent)" in block
    # placeholder + autofill + disabled contracts exist for the auth input.
    assert ".mpv1-input input::placeholder" in src
    assert ".mpv1-input input:disabled" in src or ".mpv1-input input[disabled]" in src
    assert ".mpv1-input input:-webkit-autofill" in src
    assert "-webkit-text-fill-color: var(--mp-text)" in src


def test_auth_surfaces_are_themed_not_forced_white():
    src = _css()
    # The auth card/input/right panel must not force a light background while the
    # text follows the (dark) theme — that was the invisible-text bug.
    assert ".mpv1-input {" in src
    input_container = src[src.index(".mpv1-input {"): src.index(".mpv1-input:focus-within")]
    assert "background: var(--mp-surface)" in input_container
    assert "background: #fff" not in input_container
    card = src[src.index(".mpv1-auth-card {"): src.index(".mpv1-auth-card h2")]
    assert "background: var(--mp-surface)" in card and "background: #fff" not in card


def test_field_inputs_also_have_readable_contract():
    src = _css()
    assert ".mpv1-field input," in src or ".mpv1-field input" in src
    field_area = src[src.index(".mpv1-field input"):]
    assert "color: var(--mp-text)" in field_area[:400]
    assert ".mpv1-field input:-webkit-autofill" in src


def test_forgot_password_ui_is_truthful_about_email_delivery():
    src = PUBLIC.read_text(encoding="utf-8")
    # Branches the confirmation copy on the system email-delivery capability, and
    # does not unconditionally claim an email was sent.
    assert "email_provider_configured" in src
    assert "尚未開通 Email 寄送" in src            # honest state when no provider
    assert "請聯絡管理員協助完成重設" in src
