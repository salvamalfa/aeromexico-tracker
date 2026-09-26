import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // jsdom (not "node"): several pure-function modules under test import
    // sibling modules that eagerly import the Plotly bundle, which reads
    // browser globals (self/window) at module load time.
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
  },
});
