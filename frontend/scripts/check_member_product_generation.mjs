#!/usr/bin/env node
/**
 * Automated QA: member_product_generation must be 2 (Product V2).
 * Fails the build/check if generation != 2 or DOM marker wiring is missing.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");

const issues = [];

const genFile = path.join(SRC, "product_v2", "generation.ts");
if (!fs.existsSync(genFile)) {
  issues.push("missing product_v2/generation.ts");
} else {
  const text = fs.readFileSync(genFile, "utf8");
  const m = text.match(/MEMBER_PRODUCT_GENERATION\s*=\s*(\d+)/);
  if (!m || Number(m[1]) !== 2) {
    issues.push(`member_product_generation != 2 (got ${m ? m[1] : "missing"})`);
  }
}

const appFile = path.join(SRC, "app", "NexusMemberProductV2.tsx");
if (!fs.existsSync(appFile)) {
  issues.push("missing app/NexusMemberProductV2.tsx");
} else {
  const text = fs.readFileSync(appFile, "utf8");
  if (!text.includes('data-nexus-product-generation="2"') && !text.includes("data-nexus-product-generation={MEMBER_PRODUCT_GENERATION}")) {
    issues.push("Product V2 root missing data-nexus-product-generation=2");
  }
  const bannedImports = [
    "ActualPanelOverviewPage",
    "OpportunitiesPageV1821",
    'from "../pages/MarketSymbolPage"',
    'from "../pages/ScannerPage"',
    'from "../pages/AlertsPage"',
    'from "../pages/IntelligencePage"',
    'from "../../pages/ScannerPage"',
    'from "../../pages/AlertsPage"',
    'from "../../pages/IntelligencePage"',
  ];
  for (const ban of bannedImports) {
    if (text.includes(ban)) {
      issues.push(`Product V2 imports old page-level layout: ${ban}`);
    }
  }
  if (!text.includes("MarketTerminalPageV2")) {
    issues.push("Product V2 missing MarketTerminalPageV2 route");
  }
  const oppText = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OpportunitiesPageV2.tsx"), "utf8");
  if (/>\s*L1\s*</.test(oppText) || />\s*L2\s*</.test(oppText) || />\s*L3\s*</.test(oppText)) {
    issues.push("OpportunitiesPageV2 still exposes L1/L2/L3 member UI");
  }
}

const mainFile = path.join(SRC, "main.tsx");
const mainText = fs.readFileSync(mainFile, "utf8");
if (/v1827ProductSurface|v1828ProductShell|v1829HumanProduct|v18210ProductSystem/.test(mainText)) {
  issues.push("legacy v1827/v1828/v1829/v18210 layout CSS still loaded as controlling CSS");
}
if (!mainText.includes("v18211MemberProductV2.css")) {
  issues.push("v18211MemberProductV2.css not loaded in main.tsx");
}

const appTsx = fs.readFileSync(path.join(SRC, "App.tsx"), "utf8");
if (!appTsx.includes("NexusMemberProductV2")) {
  issues.push("App.tsx does not mount NexusMemberProductV2");
}
if (/RootSurfaceSwitch[\s\S]*ActualPanelV1821App/.test(appTsx) && !appTsx.includes("NexusMemberProductV2")) {
  issues.push("default surface still ActualPanelV1821App");
}

const buildInfo = fs.readFileSync(path.join(SRC, "demo", "buildInfo.ts"), "utf8");
if (!buildInfo.includes("PUBLIC_V18_2_18_PAID_PRODUCT_VISUAL_HEAD")) {
  issues.push("buildInfo missing PUBLIC_V18_2_18_PAID_PRODUCT_VISUAL_HEAD");
}
if (!/member_product_generation:\s*2/.test(buildInfo) && !/memberProductGeneration:\s*2/.test(buildInfo)) {
  issues.push("buildInfo missing member_product_generation = 2");
}

if (issues.length) {
  console.error("FAIL member_product_generation check:");
  for (const i of issues) console.error(" -", i);
  process.exit(1);
}
console.log("PASS: member_product_generation=2 · Product V2 wiring OK");
