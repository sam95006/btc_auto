from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import RLock


class EventBus:
    def __init__(self, max_events=300):
        self._subscribers = defaultdict(list)
        self._events = deque(maxlen=max_events)
        self._lock = RLock()

    def subscribe(self, event_type, handler):
        with self._lock:
            self._subscribers[event_type].append(handler)

    def publish(self, event_type, payload=None):
        event = {
            "type": event_type,
            "payload": payload or {},
            "time": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._events.appendleft(event)
            handlers = list(self._subscribers.get(event_type, []))
            handlers += list(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                print(f"[event_bus] handler failed for {event_type}: {exc}")
        return event

    def recent(self, limit=50):
        with self._lock:
            return list(self._events)[:limit]

