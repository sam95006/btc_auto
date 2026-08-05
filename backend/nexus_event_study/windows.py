"""V14-B Event Study Engine — pre/post/control window construction."""
from __future__ import annotations

from typing import Any

from backend.nexus_event_study.definitions import require_definition
from backend.nexus_event_study.types import EventWindows, StudyEvent, WindowSpec

BAR_MS = 60_000  # synthetic bar length for fixture geometry


def build_windows(
    event: StudyEvent,
    *,
    bar_ms: int = BAR_MS,
    pre_bars: int | None = None,
    post_bars: int | None = None,
    control_bars: int | None = None,
) -> EventWindows:
    """Construct pre/post/control windows around decision_ts_ms.

    Geometry (decision bar = 0):
      pre:     [-pre_bars, 0)
      post:    [0, post_bars)
      control: [-pre_bars - control_bars, -pre_bars)
    """
    defn = require_definition(event.event_id)
    pre_n = int(pre_bars if pre_bars is not None else defn.pre_window_bars)
    post_n = int(post_bars if post_bars is not None else defn.post_window_bars)
    ctrl_n = int(control_bars if control_bars is not None else defn.control_window_bars)
    ts = int(event.decision_ts_ms)

    pre = WindowSpec(
        kind="pre",
        start_offset_bars=-pre_n,
        end_offset_bars=0,
        start_ts_ms=ts - pre_n * bar_ms,
        end_ts_ms=ts,
    )
    post = WindowSpec(
        kind="post",
        start_offset_bars=0,
        end_offset_bars=post_n,
        start_ts_ms=ts,
        end_ts_ms=ts + post_n * bar_ms,
    )
    control = WindowSpec(
        kind="control",
        start_offset_bars=-(pre_n + ctrl_n),
        end_offset_bars=-pre_n,
        start_ts_ms=ts - (pre_n + ctrl_n) * bar_ms,
        end_ts_ms=ts - pre_n * bar_ms,
    )
    return EventWindows(observation_id=event.observation_id, pre=pre, post=post, control=control)


def windows_overlap(a: EventWindows, b: EventWindows) -> bool:
    """True if post windows overlap in time (exclusive of identical endpoints)."""
    if a.post.start_ts_ms is None or a.post.end_ts_ms is None:
        return False
    if b.post.start_ts_ms is None or b.post.end_ts_ms is None:
        return False
    return a.post.start_ts_ms < b.post.end_ts_ms and b.post.start_ts_ms < a.post.end_ts_ms


def describe_window_policy() -> dict[str, Any]:
    return {
        "schema": "v14_b_window_policy",
        "pre": "[-pre_bars, 0)",
        "post": "[0, post_bars)",
        "control": "[-(pre+control), -pre)",
        "bar_ms_default": BAR_MS,
        "note": "Control is pre-period baseline; never uses future post outcomes.",
    }
