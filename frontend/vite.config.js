/** Dev server and Vitest. `/api` is proxied to the API. Coverage thresholds are enforced here. */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: "./src/testSetup.js",
    coverage: {
      provider: "v8",
      reporter: ["text"],
      include: ["src/**/*.{js,jsx}"],
      exclude: ["src/main.jsx", "src/telemetry.js", "src/**/*.test.*"],
      thresholds: {
        lines: 85,
        statements: 85,
        branches: 80,
        functions: 75,
      },
    },
  },
  server: {
    proxy: { "/api": api },
  },
  preview: {
    proxy: { "/api": api },
    allowedHosts: true,
  },
});
