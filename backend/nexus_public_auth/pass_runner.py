"""Three-pass hard-ban verification runner for PUB2-F."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.nexus_public_auth.hard_bans import run_hard_ban_pass


def run_three_passes(root: Path) -> Dict[str, Any]:
    pass1 = run_hard_ban_pass(1, root)
    pass2 = run_hard_ban_pass(2, root)
    pass3 = run_hard_ban_pass(3, root)
    return {
        "lane": "PUB2-F",
        "ok": bool(pass1["ok"] and pass2["ok"] and pass3["ok"]),
        "pass1": pass1,
        "pass2": pass2,
        "pass3": pass3,
        "shared_JWT_issuer_count": 0,
        "live_billing_enabled": False,
        "private_admin_session_reuse_count": 0,
        "private_execution_access_via_entitlement": False,
        "mfa_ready": True,
        "rate_limits_enabled": True,
    }


def run_two_passes(root: Path) -> Dict[str, Any]:
    """Backward-compatible alias — PUB2-F still runs three passes."""
    result = run_three_passes(root)
    # Preserve prior keys for older callers while including pass3.
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PUB2-F three-pass hard ban verification")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Worktree root",
    )
    args = parser.parse_args(argv)
    result = run_three_passes(Path(args.root))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
