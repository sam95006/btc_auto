// CORPORATE-1 no-fake-data guard. Fails if the Corporate frontend hardcodes
// dynamic business/market values that must come from the backend. Test/fixture
// files are exempt. Run in build:corporate.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const SCAN_DIRS = ["src/corporate", "src/surfaces/CorporateApp.tsx"];
const EXEMPT = /(__tests__|\.test\.|\.spec\.|fixtures?|\/mocks?\/)/i;

// Patterns that indicate fabricated dynamic data (not backend-driven).
const RULES = [
  { name: "dollar_price_literal", re: /\$\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\s?\d{3,}(?:\.\d+)?/ },
  { name: "standalone_percentage_literal", re: /(?<![\w.){}])\d{1,3}\.\d+\s?%/ },
  { name: "crypto_price_literal", re: /\b(?:BTC|ETH|SOL)\b[^\n{}]{0,24}?\b\d{3,}\b/ },
  { name: "hardcoded_count", re: /\b(?:members?|users?|customers?|signals?|subscribers?)\b[^\n{}]{0,16}?\b\d{2,}\b/i },
  // count written before the noun: "300+ coins", "14 signals today"
  { name: "hardcoded_count_pre", re: /\b\d{2,}\+?\s?(?:members?|users?|customers?|signals?|coins?|traders?|subscribers?)\b/i },
  { name: "market_metric_literal", re: /\b(?:regime|risk[_-]?score|readiness)\b\s*[:=]\s*["']?(?:RISK_ON|RISK_OFF|NEUTRAL|\d)/i },
  // fabricated performance/marketing figures ("99.9% uptime", "98% accuracy")
  { name: "performance_literal", re: /\b\d{2,3}(?:\.\d+)?\s?%\s?(?:uptime|accuracy|win|precision|profit|return)/i },
];

function walk(p) {
  const out = [];
  let st;
  try { st = statSync(p); } catch { return out; }
  if (st.isDirectory()) for (const c of readdirSync(p)) out.push(...walk(join(p, c)));
  else if (/\.(tsx?|jsx?)$/.test(p)) out.push(p);
  return out;
}

const files = SCAN_DIRS.flatMap((d) => walk(join(ROOT, d)));
const violations = [];
for (const f of files) {
  if (EXEMPT.test(f)) continue;
  const src = readFileSync(f, "utf8");
  src.split("\n").forEach((line, i) => {
    // Ignore comments and JSX-expression-derived values.
    const code = line.replace(/\/\/.*$/, "");
    for (const rule of RULES) {
      if (rule.re.test(code)) violations.push(`${f.replace(ROOT, "")}:${i + 1} [${rule.name}] ${line.trim().slice(0, 100)}`);
    }
  });
}

if (violations.length) {
  console.error("CORPORATE_NO_FAKE_DATA_FAIL");
  for (const v of violations) console.error("  " + v);
  process.exit(1);
}
console.log("CORPORATE_NO_FAKE_DATA_PASS");
