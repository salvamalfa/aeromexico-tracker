import { defineConfig } from "vite";

// GitHub Pages serves this site from a sub-path (/aeromexico-tracker/), so
// every asset reference must be relative — see
// docs/arquitectura/auditoria-arquitectura-20260926.md Fase 4/5.
export default defineConfig({
  base: "./",
  build: {
    outDir: "dist",
    assetsDir: "assets",
    // Deterministic output: two consecutive `npm run build` runs must
    // produce byte-identical dist/ file names (content hashes only, no
    // build timestamps) so the publication gate's manifest stays stable
    // across rebuilds of the same source.
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
    // The Vuelos map chunk pulls in plotly.js/lib/core + scattergeo/
    // choropleth traces; keep it in its own lazily-loaded chunk (see
    // web/src/views/flights/bootstrap.js dynamic import) so the initial
    // transfer for the default (reading) view stays small.
    chunkSizeWarningLimit: 900,
  },
});
