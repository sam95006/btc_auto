import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// PLATFORM-1: four independent build surfaces. Each surface has its own HTML
// entrypoint, its own route tree/root shell, and its own build output. The
// surface is selected with the NEXUS_SURFACE env var (default: personal).
const SURFACES: Record<string, { html: string; outDir: string }> = {
  personal: { html: "index.html", outDir: "dist/personal" },
  corporate: { html: "corporate.html", outDir: "dist/corporate" },
  enterprise: { html: "enterprise.html", outDir: "dist/enterprise" },
  founder: { html: "founder.html", outDir: "dist/founder" },
};

export default defineConfig(() => {
  const requested = process.env.NEXUS_SURFACE || "personal";
  const surface = SURFACES[requested] ? requested : "personal";
  const cfg = SURFACES[surface];
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: false,
      proxy: {
        "/api/market": {
          target: "http://127.0.0.1:5000",
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: cfg.outDir,
      emptyOutDir: true,
      rollupOptions: {
        input: cfg.html,
      },
    },
  };
});
