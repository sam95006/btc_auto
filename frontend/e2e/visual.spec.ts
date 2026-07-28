import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ARTIFACTS_AFTER_DIR, VIEWPORTS } from "./helpers/constants";
import { gotoRoute } from "./helpers/pageSetup";
import {
  screenshotPath,
  writeVisualManifest,
  type VisualManifestEntry,
} from "./helpers/screenshotNaming";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(__dirname, ARTIFACTS_AFTER_DIR);

const VISUAL_TARGETS: Array<{ route: string; state: string; viewport: keyof typeof VIEWPORTS }> = [
  { route: "/overview", state: "simple", viewport: "desktop" },
  { route: "/overview", state: "mobile_nav", viewport: "mobile" },
  { route: "/universe", state: "default", viewport: "desktop" },
  { route: "/alerts", state: "default", viewport: "desktop" },
  { route: "/portfolio", state: "shadow", viewport: "desktop" },
  { route: "/learning", state: "default", viewport: "desktop" },
  { route: "/evidence", state: "default", viewport: "desktop" },
  { route: "/market/BTCUSDT", state: "workbench", viewport: "desktop" },
  { route: "/founder/runtime", state: "readonly", viewport: "desktop" },
  { route: "/fleets", state: "deprecated", viewport: "desktop" },
  { route: "/overview", state: "tablet", viewport: "tablet" },
];

test.describe("@visual Wave4 screenshot capture", () => {
  test("@visual captures PNGs and manifest", async ({ page }) => {
    fs.mkdirSync(outputDir, { recursive: true });
    const entries: VisualManifestEntry[] = [];

    for (const target of VISUAL_TARGETS) {
      const vp = VIEWPORTS[target.viewport];
      await page.setViewportSize(vp);
      await gotoRoute(page, target.route);
      const filePath = screenshotPath(
        outputDir,
        target.route,
        target.state,
        vp.width,
        vp.height,
      );
      await page.screenshot({ path: filePath, fullPage: true });
      expect(fs.existsSync(filePath)).toBeTruthy();
      entries.push({
        file: path.basename(filePath),
        route: target.route,
        state: target.state,
        viewport: `${vp.width}x${vp.height}`,
        capturedAt: new Date().toISOString(),
      });
    }

    writeVisualManifest(outputDir, entries);
    expect(fs.existsSync(path.join(outputDir, "manifest.json"))).toBeTruthy();
    expect(entries.length).toBeGreaterThanOrEqual(10);
  });
});
