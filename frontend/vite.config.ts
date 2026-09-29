import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// `npm run dev`      -> app on :5173, API proxied to the FastAPI server on :8000
// `npm run build`    -> dist/ served by FastAPI in production
// `npm run build:demo` -> one self-contained HTML page that runs the engine in the browser
export default defineConfig(({ mode, command }) => ({
  base: "./",
  plugins: [react(), ...(mode === "demo" ? [viteSingleFile()] : [])],
  publicDir: mode === "demo" || command === "serve" ? "public" : false,
  optimizeDeps: { exclude: ["pyodide"] },
  define: { __DEMO_BUILD__: JSON.stringify(mode === "demo") },
  server: {
    fs: { allow: [".."] },
    proxy: { "/api": "http://localhost:8000" },
  },
  build: {
    outDir: mode === "demo" ? "dist-demo" : "dist",
    chunkSizeWarningLimit: 4000,
  },
}));
