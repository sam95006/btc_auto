from __future__ import annotations

from collections import Counter
from datetime import datetime


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class EventRegistry:
    """Central index for normalized news/events (P1 perception registry)."""

    def __init__(self, max_events=200):
        self.max_events = max(20, int(max_events))
        self._events = []
        self._index = {}

    def register_batch(self, normalized_events):
        normalized_events = list(normalized_events or [])
        for event in normalized_events:
            event_id = str(event.get("event_id") or event.get("id") or "")
            if not event_id:
                continue
            payload = {
                **event,
                "event_id": event_id,
                "registered_at": _now(),
            }
            self._index[event_id] = payload
        ordered = sorted(self._index.values(), key=lambda item: item.get("registered_at", ""), reverse=True)
        self._events = ordered[: self.max_events]
        return self.snapshot()

    def snapshot(self):
        bucket_counts = Counter(item.get("bucket", "crypto") for item in self._events)
        type_counts = Counter(item.get("event_type", "general_crypto") for item in self._events)
        major = [item for item in self._events if item.get("major")]
        return {
            "generated_at": _now(),
            "event_count": len(self._events),
            "bucket_counts": dict(bucket_counts),
            "event_type_counts": dict(type_counts),
            "major_event_count": len(major),
            "latest_major": major[:5],
            "events": self._events[:40],
        }
