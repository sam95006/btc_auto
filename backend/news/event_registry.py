from __future__ import annotations

from collections import Counter
from datetime import datetime


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class EventRegistry:
    """Central index for normalized news/events (P1 perception registry)."""

    EVENT_FLEET_ACTIONS = {
        "macro_risk": {
            "bias": "defensive",
            "watch_fleets": ["BTC", "ETH"],
            "suggested_action": "tighten_entries",
        },
        "fed_policy": {
            "bias": "defensive",
            "watch_fleets": ["BTC"],
            "suggested_action": "hedge_or_reduce_size",
        },
        "liquidation_event": {
            "bias": "defensive",
            "watch_fleets": ["RADAR", "PEPE"],
            "suggested_action": "reduce_leverage",
        },
        "exchange_risk": {
            "bias": "defensive",
            "watch_fleets": ["BTC", "ETH"],
            "suggested_action": "pause_new_entries",
        },
        "general_crypto": {
            "bias": "neutral",
            "watch_fleets": ["BTC", "ETH", "SOL"],
            "suggested_action": "monitor",
        },
    }

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

    def fleet_action_hints(self, limit=8):
        hints = []
        for event in self._events[: max(1, int(limit))]:
            event_type = str(event.get("event_type") or "general_crypto")
            template = dict(self.EVENT_FLEET_ACTIONS.get(event_type) or self.EVENT_FLEET_ACTIONS["general_crypto"])
            targets = [str(item).upper() for item in (event.get("targets") or []) if str(item).upper() != "ALL"]
            hints.append(
                {
                    "event_id": event.get("event_id"),
                    "event_type": event_type,
                    "headline": event.get("headline") or event.get("summary") or "",
                    "quality_score": event.get("quality_score"),
                    "targets": targets,
                    "bias": template.get("bias"),
                    "watch_fleets": template.get("watch_fleets"),
                    "suggested_action": template.get("suggested_action"),
                }
            )
        return hints

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
            "fleet_action_hints": self.fleet_action_hints(),
            "events": self._events[:40],
        }
