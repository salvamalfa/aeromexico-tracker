import { defineConfig, loadEnv } from "vite";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

// GitHub Pages serves this site from a sub-path (/aeromexico-tracker/), so
// every asset reference must be relative — see
// docs/arquitectura/auditoria-arquitectura-20260926.md Fase 4/5.
export default defineConfig(({ command, mode }) => {
  // Editorial candidates are opt-in: ordinary builds cannot ship a draft.
  const monthlyPreview = loadEnv(mode, process.cwd(), "VITE_").VITE_AIRLINE_MONTHLY_PREVIEW === "true";
  return ({
  base: "./",
  plugins: [{
    name: "airline-monthly-preview",
    transformIndexHtml(html, context) {
      if (!monthlyPreview || !context.filename.endsWith("/index.html")) return html;
      return html.replace('<header class="hero">', '<header class="hero"><nav aria-label="Productos"><a href="monthly.html">Airline Monthly</a></nav>');
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!monthlyPreview && req.url?.split("?")[0] === "/monthly.html") {
          res.statusCode = 404;
          res.end("Vista editorial no habilitada");
          return;
        }
        next();
      });
    },
  }],
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
        ...(monthlyPreview ? { monthly: resolve(fileURLToPath(new URL(".", import.meta.url)), "monthly.html") } : {}),
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
  });
});
