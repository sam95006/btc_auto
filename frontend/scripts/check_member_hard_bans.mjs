#!/usr/bin/env node
/**
 * PUB-D Member Platform hard-ban scanner.
 * Run TWO PASSES (pass argument 1 then 2) before commit.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");
const pass = Number(process.argv[2] || "1");

const FORBIDDEN = [
  { re: /chatgpt\.site/i, why: "runtime reference host" },
  { re: /nexus-member-platform\.s95006sam/i, why: "runtime reference URL" },
  { re: /<iframe[\s>]/i, why: "iframe element" },
  { re: /createElement\s*\(\s*['\"]iframe['\"]/i, why: "iframe createElement" },
  { re: /path=["']\/trade["']/, why: "trade route" },
  { re: /path=["']\/orders["']/, why: "orders route" },
  { re: /path=["']\/arm["']/, why: "arm route" },
  { re: /path=["']\/routing-edit["']/, why: "routing-edit route" },
  { re: /placeOrder\s*\(/, why: "placeOrder" },
  { re: /submitOrder\s*\(/, why: "submitOrder" },
  { re: /enableArm\s*\(/, why: "enableArm" },
  { re: /guaranteed\s+profit/i, why: "guaranteed profit" },
  { re: /must\s+buy/i, why: "must buy" },
  { re: /must\s+sell/i, why: "must sell" },
];

const ALLOWLIST = new Set([
  path.normalize("scripts/check_member_hard_bans.mjs"),
  path.normalize("scripts/check_ui_safety.mjs"),
]);

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

const files = [...walk(SRC), ...walk(path.join(ROOT, "scripts"))];
const issues = [];

for (const file of files) {
  const rel = path.relative(ROOT, file);
  if (ALLOWLIST.has(path.normalize(rel))) continue;
  const text = fs.readFileSync(file, "utf8");
  for (const rule of FORBIDDEN) {
    if (rule.re.test(text)) issues.push(`${rel}: ${rule.why}`);
  }
}

const app = fs.readFileSync(path.join(SRC, "App.tsx"), "utf8");
const requiredPaths = [
  "/home",
  "/market",
  "/decisions",
  "/decisions/:decisionId",
  "/evidence",
  "/counter-evidence",
  "/risk-conditions",
  "/thesis-monitor",
  "/alerts",
  "/decision-memory",
  "/outcome-review",
  "/nex-ai",
  "/membership",
  "/account",
  "/privacy",
  "/account-deletion",
  "/notification-settings",
];
for (const p of requiredPaths) {
  if (!app.includes(`path="${p}"`)) issues.push(`App.tsx missing route ${p}`);
}

const demo = fs.readFileSync(path.join(SRC, "member/demoCatalog.ts"), "utf8");
if (!demo.includes("DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE")) {
  issues.push("member/demoCatalog.ts missing DEMO SOURCE header");
}
if (!demo.includes("demo: true")) {
  issues.push("member/demoCatalog.ts missing demo:true");
}

if (issues.length) {
  console.error(`FAIL pass=${pass}`, issues);
  process.exit(1);
}
console.log(`PASS pass=${pass}: scanned ${files.length} files; member routes ok; hard bans clear`);
