// isLocalUrl (frontend/src/api/localUrl.js) against the URL table shared with the backend suite.
import { pathToFileURL, fileURLToPath } from "node:url";
import fs from "node:fs";
const root = fileURLToPath(new URL("../../frontend/src/", import.meta.url));
const { isLocalUrl } = await import(pathToFileURL(root + "api/localUrl.js").href);
const table = JSON.parse(fs.readFileSync(new URL("../fixtures/local_urls.json", import.meta.url), "utf8"));

let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + detail : "")); };

for (const [url, want] of table.cases) {
  const got = isLocalUrl(url);
  check(`isLocalUrl ${JSON.stringify(url)} -> ${want ? "local" : "cloud"}`, got === want, `got ${got}`);
}
check("isLocalUrl handles null/undefined", isLocalUrl(null) === false && isLocalUrl(undefined) === false);
process.exit(fails ? 1 : 0);
