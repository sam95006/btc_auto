"""NEXUS V16-E — Lesson Compiler.

Compiles Reflection into typed verifiable WHEN→THEN Expert action rules.
All lessons start as CANDIDATE only. Compile errors fail-closed.
Cannot emit rules that mutate production risk/leverage.
Does not write *_status.json report files. No ACTIVE real lessons.
"""
from __future__ import annotations

from backend.nexus_lesson_compiler.adversarial import run_adversarial_review
from backend.nexus_lesson_compiler.artifacts import (
    build_summary_payload,
    write_immutable_artifacts,
)
from backend.nexus_lesson_compiler.campaign import run_compiler_campaign
from backend.nexus_lesson_compiler.compiler import (
    LessonCompileError,
    assert_lessons_safe,
    compile_all_lessons,
    compile_raw_dict,
    compile_reflection,
    lesson_catalog,
)
from backend.nexus_lesson_compiler.constants import (
    CAMPAIGN_ID,
    EXPECTED_FIXTURE_COUNT,
    HARD_BANS,
    LESSON_STATUS_CANDIDATE,
    MIN_LESSON_COUNT,
    PACKAGE,
    SCHEMA,
)

__all__ = [
    "CAMPAIGN_ID",
    "EXPECTED_FIXTURE_COUNT",
    "HARD_BANS",
    "LESSON_STATUS_CANDIDATE",
    "MIN_LESSON_COUNT",
    "PACKAGE",
    "SCHEMA",
    "LessonCompileError",
    "assert_lessons_safe",
    "build_summary_payload",
    "compile_all_lessons",
    "compile_raw_dict",
    "compile_reflection",
    "lesson_catalog",
    "run_adversarial_review",
    "run_compiler_campaign",
    "write_immutable_artifacts",
]
