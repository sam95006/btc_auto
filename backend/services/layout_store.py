import json
from copy import deepcopy
from pathlib import Path


DEFAULT_LAYOUT = {
    "version": 1,
    "hotspots": {},
    "panels": {},
}

LAYOUT_PATH = Path(__file__).resolve().parents[2] / "static" / "nexus" / "layout_overrides.json"


def _normalize_payload(payload):
    base = deepcopy(DEFAULT_LAYOUT)
    if isinstance(payload, dict):
        if isinstance(payload.get("hotspots"), dict):
            base["hotspots"] = payload["hotspots"]
        if isinstance(payload.get("panels"), dict):
            base["panels"] = payload["panels"]
        if isinstance(payload.get("version"), int):
            base["version"] = payload["version"]
    return base


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
