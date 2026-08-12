"""V18.2.30 CandidateLesson replay validation — evidence-backed, no single-trade activation.

Stages remain:
CANDIDATE → REPLAY_PASS → DEVELOPMENT_PASS → SHADOW_PASS → DEMO_PASS → ACTIVE
No direct activation. Insufficient evidence → remain CANDIDATE.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

MIN_REPLAY_SAMPLE = 5
LIFECYCLE_DEFAULT = "RESEARCH_PNL_TRADE"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class LessonReplayResult:
    lesson_id: str
    mistake_signature: str | None
    sample_count: int
    would_block_bad_trade: int
    would_block_good_trade: int
    false_positive_rate: float | None
    net_effect: str
    replay_pass: bool
    lesson_stage: str
    insufficient_evidence: bool
    evaluated_at: str = field(default_factory=_utc)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_candidate_lesson_replay(
    lesson: dict[str, Any],
    *,
    historical_trades: list[dict[str, Any]],
    would_block_fn: Any | None = None,
    min_sample: int = MIN_REPLAY_SAMPLE,
) -> LessonReplayResult:
    """Validate a CandidateLesson against a set of historical ACCOUNTING_COMPLETE trades.

    Does NOT promote beyond REPLAY_PASS here. Does not activate.
    """
    lesson_id = str(lesson.get("lesson_id") or lesson.get("id") or "unknown")
    sig = lesson.get("mistake_signature") or lesson.get("signature")
    stage = str(lesson.get("state") or lesson.get("status") or "CANDIDATE").upper()
    # Exclude the originating trade if tagged
    origin = lesson.get("origin_trade_id")
    sample = [
        t
        for t in historical_trades
        if str(t.get("trade_id") or t.get("id") or "") != str(origin or "")
        and str(t.get("accounting_status") or "").upper() in {"", "ACCOUNTING_COMPLETE", "COMPLETE"}
        and str(t.get("lifecycle_purpose") or LIFECYCLE_DEFAULT) == LIFECYCLE_DEFAULT
    ]

    if len(sample) < min_sample:
        return LessonReplayResult(
            lesson_id=lesson_id,
            mistake_signature=str(sig) if sig else None,
            sample_count=len(sample),
            would_block_bad_trade=0,
            would_block_good_trade=0,
            false_positive_rate=None,
            net_effect="INSUFFICIENT_EVIDENCE",
            replay_pass=False,
            lesson_stage="CANDIDATE",
            insufficient_evidence=True,
            notes=f"need>={min_sample}_accounting_complete_trades_excluding_origin",
        )

    block_bad = 0
    block_good = 0
    for t in sample:
        is_loss = float(t.get("net_realized") or t.get("net_pnl") or 0) < 0
        is_bad_process_win = bool(t.get("BAD_PROCESS_WIN"))
        should_block = bool(is_loss or is_bad_process_win)
        blocked = False
        if callable(would_block_fn):
            blocked = bool(would_block_fn(lesson, t))
        else:
            # Heuristic: signature match on classified root cause
            t_sig = str(t.get("mistake_signature") or t.get("root_cause") or "")
            blocked = bool(sig) and t_sig == str(sig)

        if blocked and should_block:
            block_bad += 1
        elif blocked and not should_block:
            block_good += 1

    fp_denom = max(1, sum(1 for t in sample if float(t.get("net_realized") or t.get("net_pnl") or 0) >= 0))
    fp_rate = block_good / float(fp_denom)
    net = "POSITIVE" if block_bad > block_good else ("NEGATIVE" if block_good > block_bad else "NEUTRAL")
    replay_pass = block_bad >= 2 and fp_rate <= 0.25 and net in {"POSITIVE", "NEUTRAL"}

    new_stage = "REPLAY_PASS" if replay_pass and stage == "CANDIDATE" else stage
    if not replay_pass:
        new_stage = "CANDIDATE"

    return LessonReplayResult(
        lesson_id=lesson_id,
        mistake_signature=str(sig) if sig else None,
        sample_count=len(sample),
        would_block_bad_trade=block_bad,
        would_block_good_trade=block_good,
        false_positive_rate=round(fp_rate, 4),
        net_effect=net,
        replay_pass=replay_pass,
        lesson_stage=new_stage,
        insufficient_evidence=False,
        notes="no_direct_activation",
    )


def summarize_lesson_pipeline(lessons: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "candidate": 0,
        "replay_passed": 0,
        "development_passed": 0,
        "shadow_passed": 0,
        "demo_passed": 0,
        "active": 0,
    }
    for les in lessons:
        st = str(les.get("state") or les.get("status") or "CANDIDATE").upper()
        if st == "CANDIDATE":
            counts["candidate"] += 1
        elif st == "REPLAY_PASS":
            counts["replay_passed"] += 1
        elif st == "DEVELOPMENT_PASS":
            counts["development_passed"] += 1
        elif st == "SHADOW_PASS":
            counts["shadow_passed"] += 1
        elif st == "DEMO_PASS":
            counts["demo_passed"] += 1
        elif st == "ACTIVE":
            counts["active"] += 1
        else:
            counts["candidate"] += 1
    counts["repeat_after_validated_lesson"] = sum(
        int(les.get("repeat_after_validation") or les.get("repeat_after_validated_lesson") or 0)
        for les in lessons
    )
    return counts
