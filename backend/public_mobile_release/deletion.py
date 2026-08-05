"""Account deletion request state machine (public gateway only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


STATES = ("PENDING", "VERIFYING", "PURGING", "COMPLETED", "FAILED")

TRANSITIONS = {
    ("PENDING", "start_verify"): "VERIFYING",
    ("VERIFYING", "begin_purge"): "PURGING",
    ("VERIFYING", "fail"): "FAILED",
    ("PURGING", "complete"): "COMPLETED",
    ("PURGING", "fail"): "FAILED",
}

FORBIDDEN_PATH_PREFIXES = (
    "/private/",
    "/execution/",
    "/lesson-memory/",
)


@dataclass
class DeletionRequest:
    request_id: str
    user_id: str
    status: str = "PENDING"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    channel: str = "app"  # app | web


class DeletionService:
    def __init__(self, *, production_customer_db_enabled: bool = False) -> None:
        self.production_customer_db_enabled = production_customer_db_enabled
        self._requests: dict[str, DeletionRequest] = {}

    def create(self, user_id: str, *, channel: str = "app", path: str = "/v1/account/deletion-requests") -> DeletionRequest:
        if any(path.startswith(p) for p in FORBIDDEN_PATH_PREFIXES):
            raise PermissionError("private_route_forbidden")
        # Architecture may run against fixture stores; production DB remains banned in PUB-L.
        if self.production_customer_db_enabled:
            raise RuntimeError("production_customer_db_enabled_banned_in_pub_l")
        req = DeletionRequest(request_id=str(uuid4()), user_id=user_id, channel=channel)
        self._requests[req.request_id] = req
        return req

    def transition(self, request_id: str, event: str) -> DeletionRequest:
        req = self._requests[request_id]
        key = (req.status, event)
        if key not in TRANSITIONS:
            raise ValueError(f"illegal_deletion_transition:{req.status}:{event}")
        req.status = TRANSITIONS[key]
        req.updated_at = datetime.now(timezone.utc).isoformat()
        return req

    def get(self, request_id: str) -> DeletionRequest:
        return self._requests[request_id]
