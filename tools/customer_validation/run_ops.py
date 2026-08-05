#!/usr/bin/env python3
"""CLI: initialize empty workspace and run PUB2-G THREE PASS integrity proof."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.customer_validation.integrity import write_three_pass_proof, write_two_pass_proof
from tools.customer_validation.store import ensure_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PUB2-G / PUB-I customer validation ops")
    parser.add_argument(
        "--workspace",
        default=None,
        help="Local workspace path (default: tools/customer_validation/workspace)",
    )
    parser.add_argument(
        "--proof-dir",
        default=str(ROOT / "artifacts" / "customer_validation"),
        help="Directory for proof JSON (not *_status.json)",
    )
    parser.add_argument(
        "--two-pass",
        action="store_true",
        help="Also emit legacy two-pass proof for PUB-I compatibility",
    )
    args = parser.parse_args(argv)

    ws = ensure_workspace(args.workspace)
    proof_path = write_three_pass_proof(args.proof_dir, ws)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    legacy = None
    if args.two_pass:
        legacy = str(write_two_pass_proof(args.proof_dir, ws))
    print(
        json.dumps(
            {
                "ok": proof["ok"],
                "lane": "PUB2-G",
                "workspace": str(ws),
                "proof_path": str(proof_path),
                "legacy_two_pass_path": legacy,
                "pass_count": proof["pass_count"],
                "counters": proof["counters"],
                "digests_match": proof["digests_match"],
                "hard_bans_honored": proof["hard_bans_honored"],
                "status_json_emitted": False,
            },
            indent=2,
        )
    )
    return 0 if proof["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
