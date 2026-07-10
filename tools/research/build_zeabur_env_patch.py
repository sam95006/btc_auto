#!/usr/bin/env python3
"""Build Zeabur .env patch from live variable list + named patches (no secret logging)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SERVICE_ID = "6a3b81652fdef84a45a2a2a553" if False else "6a3b81652fdef84a45a2a553"
ENV_ID = "69d559b6474db8a99d6dd6bf"


def fetch_vars() -> dict[str, str]:
    cmd = (
        f'npx zeabur@latest -i=false variable list '
        f'--id {SERVICE_ID} --env-id {ENV_ID} --json'
    )
    p = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    raw = p.stdout or ""
    m = re.search(r"\{", raw)
    data = json.loads(raw[m.start() :] if m else raw)
    rows = list(data.get("variables") or []) + list(data.get("readonlyVariables") or [])
    return {str(r["key"]): str(r["value"]) for r in rows if isinstance(r, dict) and r.get("key")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--patch-json", default="{}")
    ap.add_argument("--patch-file", default="")
    args = ap.parse_args()
    if args.patch_file:
        patches = json.loads(Path(args.patch_file).read_text(encoding="utf-8-sig"))
    else:
        patches = json.loads(args.patch_json)
    vars_ = fetch_vars()
    vars_.update({str(k): str(v) for k, v in patches.items()})
    lines = [f"{k}={v}" for k, v in sorted(vars_.items())]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"keys": len(vars_), "patched": sorted(patches.keys()), "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
