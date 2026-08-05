#!/usr/bin/env node
/**
 * PUB2-C Member Web UX completion — structural + adversarial checks.
 * Usage: node scripts/check_member_ux_completion.mjs <pass>
 * Passes: 1 (structure), 2 (adversarial), 3 (independent break attempts)
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");
const pass = Number(process.argv[2] || "1");

const REQUIRED_ANSWERS = [
  "market_state",
  "best_focus",
  "largest_risk",
  "missing_confirmation",
  "when_not_to_chase",
];

const REQUIRED_STATES = [
  "fresh",
  "stale",
  "degraded",
  "pending",
  "unavailable",
  "blocked",
  "empty",
  "error",
  "loading",
];

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) {
      if (name === "node_modules" || name === "dist") continue;
      walk(p, out);
    } else if (/\.(ts|tsx|css|js|mjs|html)$/.test(name)) out.push(p);
  }
  return out;
}

const issues = [];

function fail(msg) {
  issues.push(msg);
}

// --- Pass 1: structure ---
const home = read("src/pages/member/MemberHomePage.tsx");
const first = read("src/member/firstScreenAnswers.ts");
const ux = read("src/member/uxStates.ts");
const screen = read("src/member/MemberFirstScreen.tsx");
const prefs = read("src/member/memberViewPrefs.ts");

if (!home.includes("Simple View") || !home.includes("Pro View")) {
  fail("MemberHomePage missing Simple/Pro View toggle");
}
if (!prefs.includes('"simple"') || !prefs.includes('"pro"')) {
  fail("memberViewPrefs missing simple/pro modes");
}
for (const id of REQUIRED_ANSWERS) {
  if (!first.includes(`"${id}"`) && !first.includes(`'${id}'`)) {
    fail(`firstScreenAnswers missing answer id ${id}`);
  }
}
for (const s of REQUIRED_STATES) {
  if (!ux.includes(`"${s}"`)) fail(`uxStates missing state ${s}`);
}
if (!screen.includes("member-five-answers")) {
  fail("MemberFirstScreen missing five-answers markup");
}
if (!screen.includes("member-ux-state-matrix")) {
  fail("MemberFirstScreen missing UX state matrix (Pro)");
}
if (!home.includes("Visual parity is not claimed")) {
  fail("Home must refuse visual-parity claim without screenshots");
}

// --- Pass 2: adversarial ---
if (pass >= 2) {
  const files = walk(SRC);
  for (const file of files) {
    const rel = path.relative(ROOT, file);
    const text = fs.readFileSync(file, "utf8");
    if (/chatgpt\.site/i.test(text)) fail(`${rel}: reference host banned`);
    if (/nexus-member-platform\.s95006sam/i.test(text)) fail(`${rel}: reference URL banned`);
    if (/visual parity (achieved|complete|matched)/i.test(text)) {
      fail(`${rel}: claims visual parity without screenshots`);
    }
    if (/guaranteed\s+profit/i.test(text)) fail(`${rel}: guaranteed profit ban`);
    if (/must\s+buy/i.test(text) || /must\s+sell/i.test(text)) fail(`${rel}: must buy/sell ban`);
  }

  // Unavailable must not be rendered as fabricated zero helper
  if (!ux.includes("unavailable") || !ux.includes("not fabricated")) {
    // soft: displayValueForState comment
  }
  if (!/displayValueForState[\s\S]*unavailable[\s\S]*fallbackLabel/.test(ux)) {
    fail("displayValueForState must keep unavailable off fabricated zeros");
  }

  // No lane status json artifacts under frontend for this completion
  const statusHits = walk(ROOT).filter((p) => /_status\.json$/i.test(p));
  for (const p of statusHits) {
    const rel = path.relative(ROOT, p);
    if (rel.startsWith("src") || rel.startsWith("scripts")) {
      fail(`forbidden status artifact in frontend package: ${rel}`);
    }
  }

  // State matrix builder must cover all states
  for (const s of REQUIRED_STATES) {
    if (!first.includes(`${s}:`)) {
      fail(`buildStateMatrixModels missing branch for ${s}`);
    }
  }
}

// --- Pass 3: independent break attempts ---
if (pass >= 3) {
  // Five questions must appear as user-facing labels
  const labels = [
    "Market state",
    "Best focus",
    "Largest risk",
    "Missing confirmation",
    "When not to chase",
  ];
  for (const label of labels) {
    if (!first.includes(label)) fail(`missing user-facing question label: ${label}`);
  }

  // Empty catalog path must exist (do not chase empty book)
  if (!first.includes("Do not chase an empty book") && !first.includes("empty book")) {
    fail("missing empty-book do-not-chase path");
  }

  // Loading/error must block chase language
  if (!first.includes("Do not chase while loading")) {
    fail("missing loading do-not-chase guard");
  }
  if (!first.includes("Do not chase while data is unavailable")) {
    fail("missing unavailable do-not-chase guard");
  }

  // Hard-ban scanner both passes
  for (const banPass of [1, 2]) {
    const r = spawnSync(
      process.execPath,
      [path.join(ROOT, "scripts/check_member_hard_bans.mjs"), String(banPass)],
      { encoding: "utf8" },
    );
    if (r.status !== 0) {
      fail(`hard bans pass ${banPass} failed: ${r.stdout || r.stderr}`);
    }
  }
}

if (issues.length) {
  console.error(`FAIL pass=${pass}`, issues);
  process.exit(1);
}
console.log(
  `PASS pass=${pass}: first-screen answers + Simple/Pro + ${REQUIRED_STATES.length} UX states verified`,
);
