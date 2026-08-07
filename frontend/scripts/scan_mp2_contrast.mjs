#!/usr/bin/env node
/**
 * Tiny contrast / white-on-white scan for Product V2 exchange-grade tokens.
 * Parses frontend/src/styles/v18211MemberProductV2.css token block and reports
 * WCAG-ish contrast for important text pairs. Stdout only.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const cssPath = path.resolve(__dirname, "../src/styles/v18211MemberProductV2.css");
const css = fs.readFileSync(cssPath, "utf8");

function parseHex(h) {
  const s = h.replace("#", "").trim();
  if (s.length === 3) {
    return [parseInt(s[0] + s[0], 16), parseInt(s[1] + s[1], 16), parseInt(s[2] + s[2], 16)];
  }
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}

function parseRgba(str) {
  const m = str.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/i);
  if (!m) return null;
  return {
    r: Number(m[1]),
    g: Number(m[2]),
    b: Number(m[3]),
    a: m[4] === undefined ? 1 : Number(m[4]),
  };
}

function blend(fg, bg) {
  const a = fg.a;
  return {
    r: Math.round(fg.r * a + bg.r * (1 - a)),
    g: Math.round(fg.g * a + bg.g * (1 - a)),
    b: Math.round(fg.b * a + bg.b * (1 - a)),
  };
}

function toRgb(tokenVal, tokens, bgFallback) {
  const v = tokenVal.trim();
  if (v.startsWith("#")) {
    const [r, g, b] = parseHex(v);
    return { r, g, b };
  }
  if (v.startsWith("rgba") || v.startsWith("rgb")) {
    const p = parseRgba(v);
    if (!p) return null;
    if (p.a < 1 && bgFallback) return blend(p, bgFallback);
    return { r: p.r, g: p.g, b: p.b };
  }
  if (v.startsWith("var(")) {
    const name = v.slice(4, -1).trim();
    if (tokens[name]) return toRgb(tokens[name], tokens, bgFallback);
  }
  return null;
}

function relLum({ r, g, b }) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(a, b) {
  const L1 = relLum(a);
  const L2 = relLum(b);
  const hi = Math.max(L1, L2);
  const lo = Math.min(L1, L2);
  return (hi + 0.05) / (lo + 0.05);
}

function isNearWhite({ r, g, b }) {
  return r >= 245 && g >= 245 && b >= 245;
}

// Token block under :root / .mp2-shell
const tokenRe = /--(mp2-[a-z0-9-]+)\s*:\s*([^;]+);/gi;
const tokens = {};
let m;
while ((m = tokenRe.exec(css))) {
  tokens[`--${m[1]}`] = m[2].trim();
}

const bg = toRgb(tokens["--mp2-bg"], tokens);
const surface = toRgb(tokens["--mp2-surface"], tokens);
const raised = toRgb(tokens["--mp2-surface-raised"], tokens);
const sunken = toRgb(tokens["--mp2-surface-sunken"], tokens);
const elevated = toRgb(tokens["--mp2-bg-elevated"], tokens);

const surfaces = [
  ["bg", bg],
  ["surface", surface],
  ["raised", raised],
  ["sunken", sunken],
  ["elevated", elevated],
];

let whiteOnWhite = 0;
const textTokens = [
  ["ink", tokens["--mp2-ink"]],
  ["ink-secondary", tokens["--mp2-ink-secondary"]],
  ["ink-muted", tokens["--mp2-ink-muted"]],
  ["on-primary", tokens["--mp2-on-primary"]],
];

const importantPairs = [];
for (const [sName, sRgb] of surfaces) {
  if (!sRgb) continue;
  if (isNearWhite(sRgb)) {
    // large pure-white content surface check
    console.log(`WARN surface_near_white=${sName}`);
  }
  for (const [tName, tVal] of textTokens) {
    if (tName === "on-primary") continue;
    const tRgb = toRgb(tVal, tokens, sRgb);
    if (!tRgb) continue;
    const ratio = contrast(tRgb, sRgb);
    const wow = isNearWhite(tRgb) && isNearWhite(sRgb);
    if (wow) whiteOnWhite += 1;
    importantPairs.push({ pair: `${tName}_on_${sName}`, ratio: Number(ratio.toFixed(2)), wow });
  }
}

// Primary button: on-primary on cobalt
const cobalt = toRgb(tokens["--mp2-cobalt"], tokens);
const onPrimary = toRgb(tokens["--mp2-on-primary"], tokens, cobalt);
if (cobalt && onPrimary) {
  const ratio = contrast(onPrimary, cobalt);
  importantPairs.push({ pair: "on-primary_on_cobalt", ratio: Number(ratio.toFixed(2)), wow: false });
}

const lowContrast = importantPairs.filter((p) => {
  // AA normal text ~4.5; muted on dark may be slightly softer — treat < 4.0 as fail for important
  const min = p.pair.includes("muted") ? 4.0 : 4.5;
  return p.ratio < min;
});

console.log("mp2_theme=dark");
console.log("light_mode=disabled");
console.log(`white_on_white_count=${whiteOnWhite}`);
console.log(`low_contrast_important_count=${lowContrast.length}`);
console.log(`pairs_checked=${importantPairs.length}`);
for (const p of importantPairs) {
  console.log(`  ${p.pair} ${p.ratio}:1${p.wow ? " WOW" : ""}`);
}
if (lowContrast.length) {
  console.log("contrast_status=FAIL");
  process.exitCode = 1;
} else if (whiteOnWhite > 0) {
  console.log("contrast_status=FAIL_WHITE_ON_WHITE");
  process.exitCode = 1;
} else {
  console.log("contrast_status=PASS");
}
