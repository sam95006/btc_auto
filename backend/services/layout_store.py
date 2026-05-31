import json
from copy import deepcopy
from pathlib import Path

from backend.core.data_paths import resolve_layout_path


DEFAULT_LAYOUT = {
    "version": 1,
    "hotspots": {},
    "panels": {},
}

LAYOUT_PATH = resolve_layout_path()


def _normalize_payload(payload):
    base = deepcopy(DEFAULT_LAYOUT)
    if isinstance(payload, dict):
        if isinstance(payload.get("hotspots"), dict):
            base["hotspots"] = payload["hotspots"]
        if isinstance(payload.get("panels"), dict):
            base["panels"] = _sanitize_panels(payload["panels"])
        if isinstance(payload.get("version"), int):
            base["version"] = payload["version"]
    return base


def _sanitize_panels(panels):
    """Drop panel entries that only set position without coordinates (breaks UI)."""
    cleaned = {}
    for key, saved in dict(panels or {}).items():
        if not isinstance(saved, dict):
            continue
        if any(str(saved.get(field) or "").strip() for field in ("left", "top", "right", "bottom", "width", "height")):
            cleaned[key] = saved
    return cleaned


class LayoutStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if not self.path.exists():
            return deepcopy(DEFAULT_LAYOUT)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return deepcopy(DEFAULT_LAYOUT)
        return _normalize_payload(payload)

    def save(self, payload):
        layout = _normalize_payload(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
        return layout


layout_store = LayoutStore(LAYOUT_PATH)
