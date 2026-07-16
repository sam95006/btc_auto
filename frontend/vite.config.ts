import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      // Local Vite → Flask public market proxy (MVP-22A)
      "/api/market": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
