#!/usr/bin/env node
/**
 * Optional Node mirror of tools/research/check_nexus_ui_mvp0_safety.py
 * Prefer: python tools/research/check_nexus_ui_mvp0_safety.py
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "../src");

const FORBIDDEN = [
  /path=["']\/trade["']/,
  /path=["']\/orders["']/,
  /path=["']\/arm["']/,
  /path=["']\/routing-edit["']/,
  /guaranteed\s+profit/i,
  /must\s+buy/i,
  /must\s+sell/i,
  /placeOrder/,
  /submitOrder/,
  /enableArm/,
];

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|css|js|mjs)$/.test(name)) out.push(p);
  }
  return out;
}

const files = walk(SRC);
const issues = [];

for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  for (const re of FORBIDDEN) {
    if (re.test(text)) {
      issues.push(`${path.relative(SRC, file)}: matches ${re}`);
    }
  }
}

const demo = fs.readFileSync(path.join(SRC, "demo/demoNexusData.ts"), "utf8");
if (!demo.includes("DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE")) {
  issues.push("demoNexusData.ts missing DEMO SOURCE");
}
if (!demo.includes("demo: true") && !demo.includes("demo:true")) {
  issues.push("demoNexusData.ts missing demo:true");
}

if (issues.length) {
  console.error("FAIL", issues);
  process.exit(1);
}
console.log(`PASS: scanned ${files.length} files`);
