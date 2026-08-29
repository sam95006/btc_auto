// PLATFORM-1: cross-platform per-surface build helper.
// Usage: node scripts/build_surface.mjs <corporate|personal|enterprise|founder>
// Sets NEXUS_SURFACE and invokes Vite's build API (which the vite config reads).

const SURFACES = new Set(["personal", "corporate", "enterprise", "founder"]);
const surface = process.argv[2] || "personal";
if (!SURFACES.has(surface)) {
  console.error(`build_surface: unknown surface "${surface}"`);
  process.exit(2);
}
process.env.NEXUS_SURFACE = surface;

const { build } = await import("vite");
try {
  await build();
  console.log(`SURFACE_BUILD_OK ${surface}`);
} catch (err) {
  console.error(`SURFACE_BUILD_FAILED ${surface}:`, err && err.message ? err.message : err);
  process.exit(1);
}
