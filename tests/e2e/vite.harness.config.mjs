// Vite config for the browser tests: the app's own frontend/ is the root (so /src/... and index.css are the real
// ones, and / is the real app for e2e_switch/e2e_panel), and /_harness/* is served from tests/e2e/harness/, so
// nothing is ever written into frontend/. Start it from frontend/ (Tailwind reads tailwind.config.js from the
// working directory):
//   cd frontend && npx vite --config ../tests/e2e/vite.harness.config.mjs
// Dev server only: `vite build` in frontend/ uses frontend/vite.config.js and never sees this file or the harness.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "..", "..", "frontend");
const HARNESS = path.join(HERE, "harness");
// The app's own config (plugins, base, envPrefix), imported natively so its packages resolve from frontend/
const app = (await import(pathToFileURL(path.join(FRONTEND, "vite.config.js")).href)).default;

function harness() {
  return {
    name: "avio-e2e-harness",
    resolveId(id) {
      if (id.startsWith("/_harness/")) return path.join(HARNESS, id.slice("/_harness/".length).split("?")[0]);
    },
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = (req.url || "").split("?")[0];
        if (url !== "/_harness/" && url !== "/_harness/index.html") return next();
        try {
          const html = await server.transformIndexHtml(req.url, fs.readFileSync(path.join(HARNESS, "index.html"), "utf8"));
          res.setHeader("Content-Type", "text/html");
          res.end(html);
        } catch (e) { next(e); }
      });
    },
  };
}

export default {
  ...app,
  root: FRONTEND,
  cacheDir: path.join(HERE, "node_modules", ".vite-harness"),   // leave frontend/node_modules/.vite to the app
  plugins: [...(app.plugins || []), harness()],
  server: { ...app.server, port: 5199, strictPort: true, fs: { allow: [FRONTEND, HARNESS] } },
};
