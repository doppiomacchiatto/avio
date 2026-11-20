// The Chromium-based browser the e2e scripts drive (playwright-core ships no browser).
// Override with AVIO_E2E_BROWSER; otherwise the usual Edge/Chrome install paths are tried.
import fs from "node:fs";

const candidates = [
  process.env.AVIO_E2E_BROWSER,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/microsoft-edge",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);

export const BROWSER = candidates.find((p) => fs.existsSync(p));
if (!BROWSER) throw new Error("No Edge/Chrome found: set AVIO_E2E_BROWSER to a Chromium-based browser executable.");
