"""i18n catalog parity checks (zh-TW default, English-ready)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ZH = REPO / "frontend" / "src" / "i18n" / "messages" / "zh-TW.ts"
EN = REPO / "frontend" / "src" / "i18n" / "messages" / "en.ts"

KEY_RE = re.compile(r'^\s*"([^"]+)":\s*"', re.M)


def _keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(KEY_RE.findall(text))


def check_catalog_parity() -> dict[str, Any]:
    zh_keys = _keys(ZH)
    en_keys = _keys(EN)
    missing_en = sorted(zh_keys - en_keys)
    missing_zh = sorted(en_keys - zh_keys)
    ok = not missing_en and not missing_zh and len(zh_keys) >= 40
    return {
        "ok": ok,
        "zh_key_count": len(zh_keys),
        "en_key_count": len(en_keys),
        "missing_in_en": missing_en,
        "missing_in_zh": missing_zh,
    }
