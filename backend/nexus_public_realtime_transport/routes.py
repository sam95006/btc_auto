"""Flask route helpers for PUB-F public realtime transport (LOCAL/STAGING)."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_realtime_transport.hard_bans import HardBanViolation, env_hard_ban_guard
from backend.nexus_public_realtime_transport.stream_hub import PublicStreamHub

_HUB: PublicStreamHub | None = None


def get_hub() -> PublicStreamHub:
    global _HUB
    if _HUB is None:
        hub = PublicStreamHub()
        hub.load_fixture_feed()
        _HUB = hub
    return _HUB


def reset_hub_for_tests() -> PublicStreamHub:
    global _HUB
    _HUB = PublicStreamHub()
    _HUB.load_fixture_feed()
    return _HUB


def require_local_staging() -> dict[str, Any]:
    guard = env_hard_ban_guard()
    if not guard["ok"]:
        raise HardBanViolation(f"environment_hard_ban:{guard['violations']}")
    return guard


def register_public_realtime_routes(app: Any) -> None:
    """Optional Flask registration — SSE + polling. WS frame iterator available for adapters."""
    from flask import Response, jsonify, request

    @app.get("/api/public/v1/realtime/meta")
    def public_realtime_meta():
        require_local_staging()
        return jsonify(get_hub().meta())

    @app.get("/api/public/v1/realtime/poll")
    def public_realtime_poll():
        require_local_staging()
        hub = get_hub()
        body = hub.poll(
            resume_token=request.args.get("resume_token"),
            last_event_id=request.args.get("last_event_id"),
            limit=int(request.args.get("limit") or 50),
        )
        return jsonify(body)

    @app.get("/api/public/v1/realtime/sse")
    def public_realtime_sse():
        require_local_staging()
        hub = get_hub()
        resume = request.args.get("resume_token")
        last_id = request.headers.get("Last-Event-ID") or request.args.get("last_event_id")
        max_events = min(100, max(1, int(request.args.get("max_events") or 20)))

        def generate():
            yield from hub.iter_sse(
                resume_token=resume,
                last_event_id=last_id,
                max_events=max_events,
                heartbeat_every=0.05,
            )

        resp = Response(generate(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Public-Safe"] = "true"
        resp.headers["X-Private-Event-Stream"] = "false"
        resp.headers["X-Nexus-Lane"] = "PUB-F"
        return resp

    @app.get("/api/public/v1/realtime/ws-demo-frames")
    def public_realtime_ws_demo_frames():
        """Expose WS frame encoding without opening a live production socket."""
        require_local_staging()
        hub = get_hub()
        resume = request.args.get("resume_token")
        max_events = min(50, max(1, int(request.args.get("max_events") or 10)))
        frames = list(
            hub.iter_ws_frames(
                resume_token=resume,
                max_events=max_events,
                heartbeat_every=0.05,
            )
        )
        return jsonify(
            {
                **hub.meta(),
                "transport": "websocket_frames",
                "frame_count": len(frames),
                "frames": frames,
                "note": "Frame encoding demo for LOCAL/STAGING — not a live production WS deploy.",
            }
        )
