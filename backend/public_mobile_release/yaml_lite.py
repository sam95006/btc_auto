"""YAML helpers (stdlib-only minimal subset for PUB-L gates)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return ""
    # Strip inline comments for unquoted scalars before type coercion.
    if " #" in text and not (text.startswith('"') or text.startswith("'")):
        text = text.split(" #", 1)[0].rstrip()
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text in {"null", "Null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(p.strip()) for p in inner.split(",")]
    return text


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Load a constrained YAML subset used by PUB-L config files.

    Supports: top-level mappings, nested mappings via indentation,
    lists of scalars or mappings, inline comments, booleans/ints/strings.
    Not a general YAML parser — sufficient for package gates.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    def current_container() -> Any:
        return stack[-1][1]

    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = current_container()

        if stripped.startswith("- "):
            item_raw = stripped[2:].strip()
            if isinstance(container, list):
                if ":" in item_raw and not item_raw.startswith("[") and not (
                    item_raw.startswith('"') or item_raw.startswith("'")
                ):
                    key, _, rest = item_raw.partition(":")
                    mapping: dict[str, Any] = {key.strip(): _parse_scalar(rest)}
                    container.append(mapping)
                    stack.append((indent, mapping))
                else:
                    container.append(_parse_scalar(item_raw))
            continue

        if ":" in stripped:
            key, _, rest = stripped.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest == "":
                # look ahead to decide list vs dict
                j = i
                child: Any = {}
                while j < len(lines):
                    peek = lines[j]
                    if not peek.strip() or peek.lstrip().startswith("#"):
                        j += 1
                        continue
                    peek_indent = len(peek) - len(peek.lstrip(" "))
                    if peek_indent > indent and peek.strip().startswith("- "):
                        child = []
                    break
                if isinstance(container, dict):
                    container[key] = child
                    stack.append((indent, child))
                elif isinstance(container, list):
                    # shouldn't happen often
                    mapping = {key: child}
                    container.append(mapping)
                    stack.append((indent, child))
            else:
                value = _parse_scalar(rest)
                if isinstance(container, dict):
                    container[key] = value
                elif isinstance(container, list) and container and isinstance(container[-1], dict):
                    container[-1][key] = value
            continue

    return root
