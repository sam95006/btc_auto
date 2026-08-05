#!/usr/bin/env node
/**
 * Measure Vite dist/ assets against PUB2-J performance budgets.
 * Expects `npm run build` to have produced frontend/dist.
 * Prints measured numbers; exits non-zero on budget breach.
 * Does NOT write *_status.json or report files.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const DIST = path.join(ROOT, "dist");
const require = createRequire(import.meta.url);

// Budgets mirrored from src/perf/budgets.ts (keep in sync).
const BUDGETS = {
  maxEntryJsBytes: 450_000,
  maxTotalJsBytes: 900_000,
  maxTotalCssBytes: 220_000,
  maxIndexHtmlBytes: 12_000,
};

function walkAssets(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) walkAssets(p, out);
    else out.push(p);
  }
  return out;
}

if (!fs.existsSync(DIST)) {
  console.error("FAIL: dist/ missing — run npm run build first");
  process.exit(2);
}

const assets = walkAssets(DIST);
const js = assets.filter((p) => p.endsWith(".js"));
const css = assets.filter((p) => p.endsWith(".css"));
const indexHtml = path.join(DIST, "index.html");

const jsSizes = js.map((p) => ({ file: path.relative(DIST, p), bytes: fs.statSync(p).size }));
const cssSizes = css.map((p) => ({ file: path.relative(DIST, p), bytes: fs.statSync(p).size }));
const totalJs = jsSizes.reduce((a, b) => a + b.bytes, 0);
const totalCss = cssSizes.reduce((a, b) => a + b.bytes, 0);
const entryJs = jsSizes.reduce((m, x) => (x.bytes > m.bytes ? x : m), { file: "", bytes: 0 });
const htmlBytes = fs.existsSync(indexHtml) ? fs.statSync(indexHtml).size : Number.POSITIVE_INFINITY;

const measured = {
  entryJsFile: entryJs.file,
  entryJsBytes: entryJs.bytes,
  totalJsBytes: totalJs,
  totalCssBytes: totalCss,
  indexHtmlBytes: htmlBytes,
  jsAssetCount: jsSizes.length,
  cssAssetCount: cssSizes.length,
  budgets: BUDGETS,
};

const breaches = [];
if (entryJs.bytes > BUDGETS.maxEntryJsBytes) {
  breaches.push(`entryJs ${entryJs.bytes} > ${BUDGETS.maxEntryJsBytes}`);
}
if (totalJs > BUDGETS.maxTotalJsBytes) {
  breaches.push(`totalJs ${totalJs} > ${BUDGETS.maxTotalJsBytes}`);
}
if (totalCss > BUDGETS.maxTotalCssBytes) {
  breaches.push(`totalCss ${totalCss} > ${BUDGETS.maxTotalCssBytes}`);
}
if (htmlBytes > BUDGETS.maxIndexHtmlBytes) {
  breaches.push(`indexHtml ${htmlBytes} > ${BUDGETS.maxIndexHtmlBytes}`);
}

console.log("PERF_MEASURED", JSON.stringify(measured));
if (breaches.length) {
  console.error("FAIL budget breaches:", breaches);
  process.exit(1);
}
console.log("PASS performance budgets");
