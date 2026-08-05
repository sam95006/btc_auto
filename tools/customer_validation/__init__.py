"""PUB2-G / PUB-I Customer Validation Concierge tooling.

Local/staging Founder-run ops + workflow app for 10–20 real ICP participants.
Does not create a production customer database.
Does not fabricate participants, interviews, metrics, or paid pilots.
"""

from tools.customer_validation.hard_bans import HARD_BANS, assert_hard_bans
from tools.customer_validation.integrity import (
    REQUIRED_ZERO_COUNTERS,
    compute_counters,
    run_three_pass_integrity,
    run_two_pass_integrity,
)
from tools.customer_validation.workflow_spine import WORKFLOW_STEPS, workflow_spine_status

__all__ = [
    "HARD_BANS",
    "REQUIRED_ZERO_COUNTERS",
    "WORKFLOW_STEPS",
    "assert_hard_bans",
    "compute_counters",
    "run_three_pass_integrity",
    "run_two_pass_integrity",
    "workflow_spine_status",
]
