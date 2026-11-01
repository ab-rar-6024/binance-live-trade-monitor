/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Keep the big chart library out of the first page load: it is only needed on a coin's page.
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (/recharts|d3-|victory-vendor|recharts-scale/.test(id)) return "charts";
          if (/react|scheduler/.test(id)) return "react";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
