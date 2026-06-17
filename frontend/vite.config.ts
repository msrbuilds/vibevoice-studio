import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// Proxy /api/* to the FastAPI backend so the frontend code can use relative
// URLs in dev. In production builds, set VITE_API_BASE to the backend's
// public URL.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8880",
        changeOrigin: true,
      },
    },
  },
});
