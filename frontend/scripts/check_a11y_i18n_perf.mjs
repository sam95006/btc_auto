#!/usr/bin/env node
/**
 * PUB2-J static a11y / i18n / hard-ban scanner for Member Platform sources.
 * Run with pass=1|2|3.
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
  { re: /placeOrder\s*\(/, why: "placeOrder" },
  { re: /submitOrder\s*\(/, why: "submitOrder" },
  { re: /enableArm\s*\(/, why: "enableArm" },
  { re: /guaranteed\s+profit/i, why: "guaranteed profit" },
  { re: /private_core|nexus_private|founder_private/i, why: "private core import" },
  { re: /EXCHANGE_WRITE\s*=\s*true/i, why: "exchange write enabled" },
  { re: /LIVE_BILLING\s*=\s*true/i, why: "live billing enabled" },
];

const REQUIRED_FILES = [
  "src/i18n/catalog.ts",
  "src/i18n/messages/zh-TW.ts",
  "src/i18n/messages/en.ts",
  "src/i18n/I18nProvider.tsx",
  "src/a11y/SkipToContent.tsx",
  "src/styles/a11yPerf.css",
  "src/perf/budgets.ts",
];

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

for (const rel of REQUIRED_FILES) {
  if (!fs.existsSync(path.join(ROOT, rel))) issues.push(`missing ${rel}`);
}

const indexHtml = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
if (!/lang=["']zh-Hant-TW["']/.test(indexHtml)) {
  issues.push("index.html must default lang=zh-Hant-TW");
}

const catalog = fs.readFileSync(path.join(ROOT, "src/i18n/catalog.ts"), "utf8");
if (!/DEFAULT_LOCALE:\s*LocaleCode\s*=\s*["']zh-TW["']/.test(catalog)) {
  issues.push("DEFAULT_LOCALE must be zh-TW");
}

const a11yCss = fs.readFileSync(path.join(ROOT, "src/styles/a11yPerf.css"), "utf8");
for (const token of [
  "--nx-touch-min: 44px",
  "prefers-reduced-motion",
  "prefers-contrast",
  "forced-colors",
  "nx-skip-link",
  ":focus-visible",
]) {
  if (!a11yCss.includes(token)) issues.push(`a11yPerf.css missing ${token}`);
}

const files = [...walk(SRC), ...walk(path.join(ROOT, "scripts"))];
for (const file of files) {
  const rel = path.relative(ROOT, file);
  if (rel.includes("check_a11y_i18n_perf.mjs") || rel.includes("check_member_hard_bans.mjs")) {
    continue;
  }
  const text = fs.readFileSync(file, "utf8");
  for (const rule of FORBIDDEN) {
    if (rule.re.test(text)) issues.push(`${rel}: ${rule.why}`);
  }
}

// Pass 2+: require WCAG 2.2 tags in e2e a11y specs
if (pass >= 2) {
  const a11ySpec = path.join(ROOT, "e2e", "a11y-member.spec.ts");
  if (!fs.existsSync(a11ySpec)) issues.push("missing e2e/a11y-member.spec.ts");
  else {
    const spec = fs.readFileSync(a11ySpec, "utf8");
    if (!spec.includes("wcag22aa")) issues.push("a11y-member.spec.ts missing wcag22aa tag");
    if (!spec.includes("375")) issues.push("a11y-member.spec.ts missing 375 viewport overflow check");
  }
}

// Pass 3: require measured perf script + budget constants
if (pass >= 3) {
  const measure = path.join(ROOT, "scripts", "measure_performance_budget.mjs");
  if (!fs.existsSync(measure)) issues.push("missing measure_performance_budget.mjs");
  const budgets = fs.readFileSync(path.join(ROOT, "src/perf/budgets.ts"), "utf8");
  if (!budgets.includes("maxEntryJsBytes")) issues.push("budgets.ts missing maxEntryJsBytes");
}

if (issues.length) {
  console.error(`FAIL pass=${pass}`, issues);
  process.exit(1);
}
console.log(
  `PASS pass=${pass}: a11y/i18n/perf hard bans clear; scanned ${files.length} files`,
);
