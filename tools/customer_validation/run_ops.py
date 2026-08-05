#!/usr/bin/env python3
"""CLI: initialize empty workspace and run TWO PASS integrity proof."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.customer_validation.integrity import write_two_pass_proof
from tools.customer_validation.store import ensure_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PUB-I customer validation ops")
    parser.add_argument(
        "--workspace",
        default=None,
        help="Local workspace path (default: tools/customer_validation/workspace)",
    )
    parser.add_argument(
        "--proof-dir",
        default=str(ROOT / "artifacts" / "customer_validation"),
        help="Directory for two-pass proof JSON (not *_status.json)",
    )
    args = parser.parse_args(argv)

    ws = ensure_workspace(args.workspace)
    proof_path = write_two_pass_proof(args.proof_dir, ws)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "ok": proof["ok"],
                "workspace": str(ws),
                "proof_path": str(proof_path),
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
