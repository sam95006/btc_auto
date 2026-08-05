#!/usr/bin/env python3
"""PUB2-G Concierge three-pass runner (impl digest ×3). No *_status.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_customer_validation_concierge.hard_bans import (  # noqa: E402
    refuse_status_json_write,
    require_local_staging,
    scan_owned_sources_for_private_imports,
)
from tools.customer_validation.integrity import (  # noqa: E402
    run_three_pass_integrity,
    write_three_pass_proof,
)
from tools.customer_validation.store import ensure_workspace  # noqa: E402
from tools.customer_validation.workflow_spine import workflow_spine_status  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PUB2-G Concierge three-pass ops")
    parser.add_argument("--workspace", default=None)
    parser.add_argument(
        "--proof-dir",
        default=str(ROOT / "artifacts" / "customer_validation_concierge"),
    )
    args = parser.parse_args(argv)

    env = require_local_staging()
    ws = ensure_workspace(args.workspace)
    proof_dir = Path(args.proof_dir)
    refuse_status_json_write(proof_dir / "customer_validation_concierge_three_pass_proof.json")
    proof_path = write_three_pass_proof(proof_dir, ws)
    proof = run_three_pass_integrity(ws)
    spine = workflow_spine_status(ws)
    import_violations = scan_owned_sources_for_private_imports(ROOT)

    result = {
        "ok": proof["ok"] and not import_violations and spine["all_required_zeros"],
        "lane": "PUB2-G",
        "environment": env["environment"],
        "workspace": str(ws),
        "proof_path": str(proof_path),
        "pass_count": 3,
        "digests_match": proof["digests_match"],
        "counters": proof["counters"],
        "workflow_steps": spine["step_ids"],
        "hard_bans_honored": proof["hard_bans_honored"],
        "private_import_violations": import_violations,
        "status_json_emitted": False,
        "note": "Counters remain 0 until real people participate.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
