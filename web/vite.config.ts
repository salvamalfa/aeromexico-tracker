import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { readFile } from "node:fs/promises";

// GitHub Pages serves this site from a sub-path (/aeromexico-tracker/), so
// every asset reference must be relative — see
// docs/arquitectura/auditoria-arquitectura-20260926.md Fase 4/5.
export default defineConfig(({ command }) => ({
  plugins: command === "serve" ? [{
    name: "local-editorial-review",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const match = req.url?.match(/^\/__editorial-review\/(\d{4}Q[1-4])\.json$/);
        if (!match) return next();
        try {
          const path = fileURLToPath(new URL(`../tmp/editorial-rerun/${match[1]}.json`, import.meta.url));
          const raw = await readFile(path);
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.setHeader("Cache-Control", "no-store");
          res.end(raw);
        } catch { res.statusCode = 404; res.end(); }
      });
    },
  }] : [],
  base: "./",
  // plotly.js' has-hover dependency reads the Node-style `global` name. The
  // production build already rewrites it (Rollup's CommonJS plugin), but the
  // dev server's dependency pre-bundling does not, so the alias applies only
  // to `vite` (serve). Keeping it out of `vite build` leaves the published
  // bundle byte-identical to a build without the chat panel.
  ...(command === "serve" ? { define: { global: "globalThis" } } : {}),
  build: {
    outDir: "dist",
    assetsDir: "assets",
    // Deterministic output: two consecutive `npm run build` runs must
    // produce byte-identical dist/ file names (content hashes only, no
    // build timestamps) so the publication gate's manifest stays stable
    // across rebuilds of the same source.
    rollupOptions: {
      input: {
        dashboard: resolve(fileURLToPath(new URL(".", import.meta.url)), "index.html"),
        review: resolve(fileURLToPath(new URL(".", import.meta.url)), "review.html"),
        access: resolve(fileURLToPath(new URL(".", import.meta.url)), "access.html"),
      },
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
}));
