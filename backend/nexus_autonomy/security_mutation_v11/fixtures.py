"""Filesystem / fuzz / import attack fixtures for V11 mutation red team."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


def build_filesystem_attack_tree(root: Path) -> dict[str, Any]:
    """Create local-only attack fixtures (no network, no secrets written in clear for artifacts)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    sandbox = root / "sandbox"
    sandbox.mkdir(exist_ok=True)
    (sandbox / "legit").mkdir(exist_ok=True)
    (sandbox / "legit" / "ok.json").write_text('{"ok":true}\n', encoding="utf-8")

    outside = root / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("REDACTED_FIXTURE_NOT_A_REAL_SECRET\n", encoding="utf-8")

    evil_names = [
        "../outside/secret.txt",
        "..\\outside\\secret.txt",
        "legit/../../outside/secret.txt",
        "legit/./../../outside/secret.txt",
        "/etc/passwd",
        "C:\\Windows\\System32\\config\\SAM",
        "legit/\x00evil",
        "legit/" + ("a" * 4000),
    ]
    manifest = {
        "sandbox": str(sandbox),
        "outside": str(outside),
        "traversal_vectors": evil_names,
        "pickle_fixture": str(root / "evil.pkl"),
        "corrupt_json": str(root / "corrupt.json"),
        "scalar_json": str(root / "scalar.json"),
    }
    # Classic pickle protocol header only — never executed
    (root / "evil.pkl").write_bytes(b"\x80\x04\x95\x00\x00\x00\x00\x00\x00\x00\x00c")
    (root / "corrupt.json").write_bytes(b'{"events":[{"type":"X"')
    (root / "scalar.json").write_text("null\n", encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def fuzz_path_vectors(seed: int = 11, n: int = 64) -> list[str]:
    rng = random.Random(seed)
    parts = ["..", ".", "legit", "outside", "etc", "passwd", "secret.txt", "a", "b"]
    seps = ["/", "\\", "/./", "/../"]
    out: list[str] = []
    for _ in range(n):
        depth = rng.randint(1, 8)
        chunks = [rng.choice(parts) for _ in range(depth)]
        s = chunks[0]
        for c in chunks[1:]:
            s += rng.choice(seps) + c
        if rng.random() < 0.1:
            s = "\x00" + s
        out.append(s)
    return out


def fuzz_json_blobs(seed: int = 22, n: int = 32) -> list[Any]:
    rng = random.Random(seed)
    samples: list[Any] = [
        None,
        True,
        0,
        1,
        -1,
        "",
        "cos\nsystem\n",
        {"events": []},
        {"api_key": "x" * 24},
        {"payload": {"raw_provider_prompt": "x"}},
    ]
    for i in range(n):
        kind = rng.choice(["obj", "list", "scalar", "corrupt"])
        if kind == "obj":
            samples.append({"k": i, "v": rng.random()})
        elif kind == "list":
            samples.append([i, "x", None])
        elif kind == "scalar":
            samples.append(rng.choice([None, 3, "s", True]))
        else:
            samples.append("{not-json-" + str(i))
    return samples
