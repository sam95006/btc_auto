import fs from "node:fs";
import path from "node:path";

export function routeSlug(route: string): string {
  const trimmed = route.replace(/^\//, "").replace(/\/$/, "");
  if (!trimmed) return "root";
  return trimmed.replace(/\//g, "_").replace(/:/g, "");
}

export function screenshotFileName(
  route: string,
  state: string,
  width: number,
  height: number,
): string {
  return `${routeSlug(route)}_${state}_${width}x${height}.png`;
}

export function screenshotPath(
  baseDir: string,
  route: string,
  state: string,
  width: number,
  height: number,
): string {
  return path.join(baseDir, screenshotFileName(route, state, width, height));
}

export type VisualManifestEntry = {
  file: string;
  route: string;
  state: string;
  viewport: string;
  capturedAt: string;
};

export function writeVisualManifest(
  baseDir: string,
  entries: VisualManifestEntry[],
): void {
  fs.mkdirSync(baseDir, { recursive: true });
  const manifestPath = path.join(baseDir, "manifest.json");
  const payload = {
    schema_version: "wave4_visual_capture_manifest_v1",
    capturedAt: new Date().toISOString(),
    entries,
  };
  fs.writeFileSync(manifestPath, JSON.stringify(payload, null, 2), "utf-8");
}
