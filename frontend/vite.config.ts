import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const tauriBackendPort = process.env.DBA_TAURI_DEV_BACKEND_PORT;
const backend = `http://127.0.0.1:${tauriBackendPort ?? "8686"}`;

export default defineConfig(({ command }) => ({
  base: command === "serve" && tauriBackendPort ? "/" : "/app-assets/",
  plugins: [react()],
  build: {
    outDir: "../server/frontend_dist",
    assetsDir: "",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": backend, ...(tauriBackendPort && { "/preview-file": backend }) },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
}));
