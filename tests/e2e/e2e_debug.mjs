// The debug log: one store, shown in the dock at the bottom of every tab (components/DebugDock.jsx) and,
// on the startup org picker, in an overlay. Needs the backend on 7893 and `vite --port 5199` in frontend/. Orgs are mocked.
import { chromium } from "playwright-core";
import { BROWSER } from "./browser.mjs";

const APP = "http://localhost:5199/";
let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail !== "" ? "  -- " + String(detail).slice(0, 300) : "")); };

const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" };
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => { if (!/transformCallback/.test(String(e))) errors.push(String(e)); });
await page.addInitScript(() => { window.__SF_BACKEND_PORT__ = 7893; localStorage.setItem("avio_welcome_seen_v1", "1"); });
await page.route(/\/api\/(sf-version|orgs)(\/.*)?(\?.*)?$/, (route) => {
  const req = route.request();
  if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
  const u = new URL(req.url()).pathname;
  let body = {};
  if (u === "/api/sf-version") body = { version: "stub" };
  else if (u === "/api/orgs") body = { orgs: [{ alias: "org-one", username: "one@example.com", isDefault: true }] };
  else if (u.endsWith("/objects")) body = { objects: [] };
  else if (u.endsWith("/limits")) body = { dailyApiRequests: { used: 1, max: 100 } };
  return route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(body) });
});

const connect = page.getByRole("button", { name: "Connect to org" });
const tab = (name) => page.getByRole("button", { name: new RegExp(name) }).first().click();
const bug = () => page.getByRole("button", { name: /^🐞 Debug( \(\d+\))?$/ });
const dockHeight = () => page.evaluate(() => Math.round(document.getElementById("debug").getBoundingClientRect().height));
const dockText = () => page.locator("#debug").innerText();
const dockSep = () => page.locator('[role="separator"][title^="Drag to resize the debug log"]');
const log = (msg, level) => page.evaluate(async ([m, l]) => (await import("/src/debugLog.js")).debugLog(m, l), [msg, level]);
const scope = (name) => page.locator("#debug").getByRole("button", { name, exact: true }).click();
const near = (a, b, tol = 3) => Math.abs(a - b) <= tol;
const settle = () => page.waitForTimeout(250);

// ── startup: the org picker's link shows the same log in an overlay ─────────
await page.goto(APP);
await connect.waitFor();
await page.getByRole("button", { name: /^🐞 Debug log/ }).click();
const dialog = page.getByRole("dialog", { name: "Debug log" });
await dialog.waitFor();
const startup = await dialog.innerText();
check("org picker: the overlay shows the startup entries", /\[OrgPicker\]|GET \/api/.test(startup), startup);
await page.keyboard.press("Escape");
await dialog.waitFor({ state: "hidden" });
check("org picker: Escape closes the overlay", true);
await connect.click();

// ── the dock ─────────────────────────────────────────────────────────────────
await page.locator("#debug").waitFor();
await settle();
check("the dock starts collapsed to its header", near(await dockHeight(), 28, 2), await dockHeight());
check("only one debug log on the page (the per-tab panels are gone)", (await page.getByText(/Debug Log/).count()) === 1, await page.getByText(/Debug Log/).count());
await bug().click();
await settle();
check("the 🐞 button opens the dock at the default height", near(await dockHeight(), 200, 3), await dockHeight());
check("the 🐞 button shows it is pressed", (await bug().getAttribute("aria-pressed")) === "true");
let text = await dockText();
check("API requests are logged (This tab)", /GET \/api\//.test(text), text);
await bug().click();
await settle();
check("the 🐞 button closes it again", near(await dockHeight(), 28, 2), await dockHeight());

await log("probe error from the FLS tab", "error");
await settle();
check("a logged error opens the dock", near(await dockHeight(), 200, 3), await dockHeight());
check("and shows the entry", (await dockText()).includes("probe error from the FLS tab"));

// switching tabs: This tab / All
await tab("SOQL Runner");
await page.locator("textarea").first().waitFor();
await log("probe from the SOQL tab", "success");
await settle();
text = await dockText();
check("This tab: the SOQL tab's entry shows", text.includes("probe from the SOQL tab"), text);
check("This tab: the FLS tab's entry does not", !text.includes("probe error from the FLS tab"), text);
await scope("All");
text = await dockText();
check("All: entries from every tab, tagged with the tab", text.includes("[fls]") && text.includes("probe error from the FLS tab") && text.includes("probe from the SOQL tab"), text);

// filter
await page.locator("#debug").getByLabel("Filter log entries").fill("probe from");
text = await dockText();
check("the filter narrows the list", text.includes("probe from the SOQL tab") && !text.includes("probe error from the FLS tab"), text);
await page.locator("#debug").getByLabel("Filter log entries").fill("");

// Clear in This tab only clears this tab
await scope("This tab");
await page.locator("#debug").getByRole("button", { name: "Clear" }).click();
await scope("All");
text = await dockText();
check("Clear in This tab keeps the other tabs' entries", text.includes("probe error from the FLS tab") && !text.includes("probe from the SOQL tab"), text);

// opening and closing the dock does not remount the page
const editor = page.locator("textarea").first();
await editor.fill("SELECT Id FROM Account -- kept");
await bug().click();
await settle();
await bug().click();
await settle();
check("toggling the dock keeps the page's state", (await editor.inputValue()) === "SELECT Id FROM Account -- kept", await editor.inputValue());

// resize, limits, remembered
const b = await dockSep().boundingBox();
const x = 400, y = b.y + b.height / 2;
await page.mouse.move(x, y);
await page.mouse.down();
await page.mouse.move(x, y - 60, { steps: 4 });
await page.mouse.move(x, y - 120, { steps: 4 });
await page.mouse.up();
await settle();
const tall = await dockHeight();
check("dragging the divider up makes the dock taller", near(tall, 320, 4), tall);
await page.mouse.move(x, y - 120);
await page.mouse.down();
await page.mouse.move(x, 0, { steps: 6 });
await page.mouse.up();
await settle();
const page0 = await page.evaluate(() => Math.round(document.getElementById("page").getBoundingClientRect().height));
check("the page keeps at least 160px", page0 >= 159, page0);
const b2 = await dockSep().boundingBox();
await page.mouse.move(x, b2.y + b2.height / 2);
await page.mouse.down();
const dockBottom = await page.evaluate(() => document.getElementById("debug").getBoundingClientRect().bottom);
await page.mouse.move(x, dockBottom - 180 - b2.height / 2, { steps: 6 });   // to about 180px
await page.mouse.up();
await settle();
const kept = await dockHeight();
check("a height was chosen", near(kept, 180, 6), kept);

await page.goto(APP);                                 // reload = a new launch
await connect.waitFor();
await connect.click();
await page.locator("#debug").waitFor();
await settle();
check("after a reload the dock starts collapsed", near(await dockHeight(), 28, 2), await dockHeight());
await bug().click();
await settle();
check("and opens at the remembered height", near(await dockHeight(), kept, 3), `${await dockHeight()} vs ${kept}`);

// dragging it down past its minimum collapses it
const b3 = await dockSep().boundingBox();
await page.mouse.move(x, b3.y + 2);
await page.mouse.down();
await page.mouse.move(x, 715, { steps: 6 });
await page.mouse.up();
await settle();
check("dragging it to the bottom collapses it", near(await dockHeight(), 28, 2), await dockHeight());
check("and the 🐞 button follows", (await bug().getAttribute("aria-pressed")) === "false");

check("no page errors", errors.length === 0, errors.join(" | "));
await browser.close();
