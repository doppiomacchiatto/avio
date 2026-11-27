// The AI side panel of the Apex Runner and SOQL Runner: one shared width, resizable, remembered.
// Needs the backend on 7893 (isolated APPDATA, no token) and `vite --port 5199` in frontend/. Orgs are mocked.
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

async function start() {
  await page.goto(APP);
  await page.getByRole("button", { name: "Connect to org" }).waitFor();
  await page.getByRole("button", { name: "Connect to org" }).click();
}
const tab = (name) => page.getByRole("button", { name: new RegExp(name) }).first().click();
// the AI panel's divider (the debug dock at the bottom has one too)
const AI_SEP = '[role="separator"][title^="Drag to resize the AI panel"]';
const sep = () => page.locator(AI_SEP);
const aiToggle = () => page.getByRole("button", { name: /^\S* ?AI$/ });
const openAi = async () => { if (!(await sep().count())) await aiToggle().first().click(); await sep().waitFor(); };
const width = () => page.evaluate(() => Math.round(document.getElementById("ai").getBoundingClientRect().width));
const restWidth = () => page.evaluate(() => Math.round(document.getElementById("main").getBoundingClientRect().width));
const groupWidth = () => page.evaluate(() => document.getElementById("main").closest("[data-group]").getBoundingClientRect().width);
async function drag(dx) {
  const b = await sep().boundingBox();
  const x = b.x + b.width / 2, y = b.y + 200;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx / 2, y, { steps: 4 });
  await page.mouse.move(x + dx, y, { steps: 4 });
  await page.mouse.up();
}
const near = (a, b, tol = 3) => Math.abs(a - b) <= tol;

await start();
await tab("Apex Runner");
await openAi();
const apex0 = await width();
check("Apex Runner: the panel opens at the default width (480)", near(apex0, 480, 1), apex0);
await tab("SOQL Runner");
await openAi();
const soql0 = await width();
check("SOQL Runner: the panel has the same width", near(soql0, apex0, 1), `${soql0} vs ${apex0}`);

await drag(-150);
const soql1 = await width();
check("dragging the divider to the left widens the panel", near(soql1, 630), soql1);
check("the editor side keeps the rest of the window", (await restWidth()) >= 240, await restWidth());
await tab("Apex Runner");
await sep().waitFor();
check("Apex Runner follows the width set in the SOQL Runner", near(await width(), soql1, 1), await width());
await drag(100);
const apex1 = await width();
check("dragging to the right narrows it", near(apex1, 530), apex1);
await tab("SOQL Runner");
await sep().waitFor();
check("SOQL Runner follows the width set in the Apex Runner", near(await width(), apex1, 1), await width());

await tab("Apex Runner");
await sep().waitFor();
await drag(-2000);
const gw = await groupWidth();
check("it cannot grow past 70% of the split (the divider is 6px)", near(await width(), (gw - 6) * 0.7, 3), `${await width()} of ${gw}`);
await drag(2000);
check("it cannot shrink below 320", near(await width(), 320, 1), await width());
await sep().dblclick();
check("double-click resets to the default", near(await width(), 480, 1), await width());
await sep().focus();
const beforeKey = await width();
await page.keyboard.press("ArrowLeft");
check("arrow keys resize it", (await width()) !== beforeKey, `${beforeKey} -> ${await width()}`);
// the divider shows its state in both themes
const sepColor = () => sep().evaluate((el) => getComputedStyle(el).backgroundColor);
const BLUE = "rgb(59, 130, 246)";
for (const dark of [false, true]) {
  await page.evaluate((d) => document.documentElement.classList.toggle("dark", d), dark);
  await page.mouse.move(100, 400);
  await sep().evaluate((el) => el.blur());
  await page.waitForTimeout(300);
  const idle = await sepColor();
  const b = await sep().boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + 200);
  await page.waitForTimeout(300);
  const hover = await sepColor();
  await page.mouse.down();
  await page.waitForTimeout(300);
  const active = await sepColor();
  await page.mouse.up();
  check(`${dark ? "dark" : "light"} theme: the divider is grey when idle and blue on hover and while dragging`, idle !== BLUE && hover === BLUE && active === BLUE, `idle ${idle}, hover ${hover}, active ${active}`);
}
await page.evaluate(() => document.documentElement.classList.remove("dark"));
await page.mouse.move(100, 400);
check("the text on the page is not selected by dragging", (await page.evaluate(() => String(window.getSelection()))) === "");

await sep().dblclick();
await drag(-200);
const kept = await width();
check("a width was chosen", near(kept, 680), kept);
await page.setViewportSize({ width: 800, height: 720 });
// the library can show a proportional width for a moment before it clamps: wait for the clamp, not just for "smaller"
await page.waitForFunction(() => Math.abs(document.getElementById("ai").getBoundingClientRect().width - (800 - 6) * 0.7) <= 3, null, { timeout: 5000 }).catch(() => {});
check("a smaller window clamps the panel to 70%", near(await width(), (800 - 6) * 0.7, 3), await width());
check("and the editor keeps a usable width", (await restWidth()) >= 230, await restWidth());
await page.setViewportSize({ width: 1280, height: 720 });
await tab("SOQL Runner");
await sep().waitFor();
await tab("Apex Runner");
await sep().waitFor();
check("the chosen width (not the clamped one) is used again once the window is large", near(await width(), kept, 1), `${await width()} vs ${kept}`);

// closing and reopening the panel in the same tab keeps the width
await aiToggle().first().click();
await page.waitForFunction((sel) => !document.querySelector(sel), AI_SEP);
check("with the panel closed the editor takes the whole width", near(await restWidth(), await groupWidth(), 1), `${await restWidth()} of ${await groupWidth()}`);
await aiToggle().first().click();
await sep().waitFor();
check("reopening the panel keeps the chosen width", near(await width(), kept, 1), `${await width()} vs ${kept}`);

await start();                                        // reload = a new launch
await tab("Apex Runner");
await openAi();
check("the width is remembered after a reload", near(await width(), kept, 1), `${await width()} vs ${kept}`);
await tab("SOQL Runner");
await openAi();
check("and in the SOQL Runner too", near(await width(), kept, 1), `${await width()} vs ${kept}`);
check("no page errors", errors.length === 0, errors.join(" | "));

await browser.close();
console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
