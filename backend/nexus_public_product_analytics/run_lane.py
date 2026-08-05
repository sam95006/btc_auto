#!/usr/bin/env python3
"""CLI: emit metric schema + run THREE PASS proof (no *_status.json)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_product_analytics.schema import build_metric_schema
from backend.nexus_public_product_analytics.three_pass import write_three_pass_proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PUB2-I product analytics lane runner")
    parser.add_argument("--root", default=str(ROOT), help="Worktree root")
    parser.add_argument(
        "--proof-dir",
        default=None,
        help="Directory for three-pass proof JSON (not *_status.json)",
    )
    parser.add_argument(
        "--write-schema",
        action="store_true",
        help="Write canonical metric schema JSON under docs/product_analytics/",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)

    schema = build_metric_schema()
    schema_path = (
        root / "docs" / "product_analytics" / "NEXUS_PUBLIC_V2_PRODUCT_ANALYTICS_METRIC_SCHEMA_V1.json"
    )
    if args.write_schema:
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    proof_dir = Path(args.proof_dir) if args.proof_dir else root / "artifacts" / "product_analytics"
    proof_path = write_three_pass_proof(root, proof_dir)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "ok": proof["ok"],
                "lane": proof["lane"],
                "schema_path": str(schema_path),
                "schema_written": bool(args.write_schema),
                "north_star": schema["north_star"]["name"],
                "metric_ids": [m["metric_id"] for m in schema["metrics"]],
                "proof_path": str(proof_path),
                "pass1_ok": proof["pass1"]["ok"],
                "pass2_ok": proof["pass2"]["ok"],
                "pass3_ok": proof["pass3"]["ok"],
                "status_json_emitted": False,
                "fabricated_metrics": False,
            },
            indent=2,
        )
    )
    return 0 if proof["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
