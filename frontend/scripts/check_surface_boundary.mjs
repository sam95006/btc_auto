// PLATFORM-1 public/private boundary check.
// Recursively follows the import graph from each PUBLIC surface entrypoint
// (personal, corporate, enterprise) and fails if it reaches the Founder private
// tree (src/founder/**, src/pages/FounderRuntimePage, or the FounderApp surface).
// The founder-private entrypoint is intentionally NOT checked.

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src", import.meta.url));

const PUBLIC_ENTRIES = [
  "main.tsx", // personal
  "entries/corporateMain.tsx",
  "entries/enterpriseMain.tsx",
];

// Any reached file whose path matches these is a boundary violation for a
// public surface.
const FORBIDDEN_PATH = /[\\/](founder[\\/]|pages[\\/]FounderRuntimePage|surfaces[\\/]FounderApp)/i;

function resolveImport(fromFile, spec) {
  if (!spec.startsWith(".")) return null; // external package
  const base = resolve(dirname(fromFile), spec);
  const candidates = [
    base,
    `${base}.tsx`,
    `${base}.ts`,
    `${base}.jsx`,
    `${base}.js`,
    resolve(base, "index.tsx"),
    resolve(base, "index.ts"),
  ];
  return candidates.find((c) => existsSync(c)) || null;
}

function scan(entryRel) {
  const start = resolve(SRC, entryRel);
  const seen = new Set();
  const stack = [start];
  const violations = [];
  while (stack.length) {
    const f = stack.pop();
    if (seen.has(f)) continue;
    seen.add(f);
    if (FORBIDDEN_PATH.test(f)) {
      violations.push(f);
      continue;
    }
    let src;
    try {
      src = readFileSync(f, "utf-8");
    } catch {
      continue;
    }
    const re = /(?:import|export)[^"']*?["']([^"']+)["']/g;
    let m;
    while ((m = re.exec(src))) {
      const resolved = resolveImport(f, m[1]);
      if (resolved) stack.push(resolved);
    }
  }
  return violations;
}

let failed = false;
for (const entry of PUBLIC_ENTRIES) {
  const v = scan(entry);
  if (v.length) {
    failed = true;
    console.error(`SURFACE_BOUNDARY_FAIL: public entry ${entry} reaches private founder code:`);
    for (const f of v) console.error(`  - ${f.replace(SRC, "src")}`);
  } else {
    console.log(`SURFACE_BOUNDARY_OK ${entry}`);
  }
}
if (failed) {
  console.error("Public surfaces must not import the Founder private tree.");
  process.exit(1);
}
console.log("SURFACE_BOUNDARY_PASS");
