// Record Counts in the real App: the SOQL Runner's Counts button and the AI Chat's Record Counts action both
// run one SELECT COUNT() per object and show the result. Orgs, objects and /api/soql are mocked per object.
// Needs the backend on 7893 (isolated APPDATA, no token) and vite on 5199, like the other e2e scripts.
import { chromium } from "playwright-core";
import { BROWSER } from "./browser.mjs";

const APP = "http://localhost:5199/";
let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail !== "" ? "  -- " + String(detail).slice(0, 300) : "")); };

const CORE = { Account: 500, Contact: 1200, Lead: 0, Opportunity: 300, Case: 300, Task: 4000, Event: 10, User: 25 };
const CUSTOM = Array.from({ length: 25 }, (_, i) => `Obj${String(i).padStart(2, "0")}__c`);   // more than the cap of 20
const customCount = (n) => (n === "Obj00__c" ? 2000 : 7);
const FAILING = "Obj03__c";

const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" };
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
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
  else if (u.endsWith("/objects")) body = { objects: [...Object.keys(CORE), "Foo__mdt", ...CUSTOM].map((n) => ({ apiName: n, label: n, custom: n.endsWith("__c") })) };
  else if (u.endsWith("/limits")) body = { dailyApiRequests: { used: 1, max: 100 } };
  return route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(body) });
});

let queries = [], inFlight = 0, peak = 0;
await page.route(/\/api\/soql$/, async (route) => {
  const req = route.request();
  if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
  const { query, alias } = JSON.parse(req.postData() || "{}");
  queries.push({ query, alias });
  inFlight++; peak = Math.max(peak, inFlight);
  await new Promise((r) => setTimeout(r, 120));
  inFlight--;
  const name = (query.match(/^SELECT COUNT\(\) FROM (\w+)$/) || [])[1];
  if (name === FAILING)
    return route.fulfill({ status: 500, headers: CORS, contentType: "application/json", body: JSON.stringify({ detail: `sObject type '${FAILING}' is not supported.` }) });
  const total = name in CORE ? CORE[name] : customCount(name);
  return route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify({ records: [], totalSize: total }) });
});

let aiBody = null;
await page.route(/\/api\/ai\/chat$/, (route) => {
  const req = route.request();
  if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
  aiBody = JSON.parse(req.postData() || "{}");
  return route.fulfill({ status: 500, headers: CORS, contentType: "application/json", body: JSON.stringify({ detail: "e2e: no AI here" }) });
});

await page.goto(APP);
await page.getByRole("button", { name: "Connect to org" }).waitFor();
await page.getByRole("button", { name: "Connect to org" }).click();
const tab = (name) => page.getByRole("button", { name: new RegExp(name) }).first().click();

const queried = () => queries.map((q) => q.query.replace("SELECT COUNT() FROM ", ""));
function checkQuerySet(where) {
  const names = queried();
  check(`${where}: one COUNT() query per object, all for org-one`, queries.every((q) => /^SELECT COUNT\(\) FROM \w+$/.test(q.query) && q.alias === "org-one"), JSON.stringify(queries.slice(0, 3)));
  check(`${where}: the 8 core objects and exactly 20 custom objects (cap)`, names.length === 28 && Object.keys(CORE).every((n) => names.includes(n))
    && names.filter((n) => n.endsWith("__c")).length === 20 && !names.includes("Obj20__c") && !names.includes("Foo__mdt"), names.join(","));
  check(`${where}: at most 4 queries at a time`, peak <= 4 && peak > 1, peak);
}

// ---- SOQL Runner: Counts button ------------------------------------------------------------------------
await tab("AI Chat");                               // AI Chat loads the org's object list in the background
await page.waitForTimeout(800);
await tab("SOQL Runner");
const counts = page.locator('button[title^="Run COUNT()"]');   // by title: while counting its text is a spinner
await counts.waitFor();
await page.getByText("Obj00__c").first().waitFor({ timeout: 10000 });   // the custom objects are in the list
await counts.click();
await page.waitForTimeout(150);
check("SOQL Runner: Counts is disabled while counting", await counts.isDisabled());
check("SOQL Runner: Run is disabled while counting", await page.getByRole("button", { name: /▶ Run/ }).isDisabled());
await page.waitForFunction(() => [...document.querySelectorAll("td")].some((td) => td.textContent === "Task"), null, { timeout: 15000 });
await page.waitForTimeout(200);
checkQuerySet("SOQL Runner");
const table = await page.evaluate(() => [...document.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent.trim())).filter((r) => r.length >= 3));
check("SOQL Runner: rows sorted by count (Task, Obj00__c, Contact, Account first)", table.length >= 28
  && ["Task", "Obj00__c", "Contact", "Account"].every((n, i) => table[i].includes(n)), JSON.stringify(table.slice(0, 4)));
check("SOQL Runner: counts are formatted (4,000)", table[0].includes("4,000"), JSON.stringify(table[0]));
const failRow = table.find((r) => r.includes(FAILING));
check("SOQL Runner: the failed object has a note and the others still show", !!failRow && failRow.some((c) => c.includes("not supported")) && table.length >= 28, JSON.stringify(failRow));
check("SOQL Runner: Counts and Run enabled again afterwards", !(await counts.isDisabled()) && !(await page.getByRole("button", { name: /▶ Run/ }).isDisabled()));

// ---- AI Chat: Record Counts runs the queries and posts a report ---------------------------------------------
queries = []; peak = 0;
await tab("AI Chat");
const chip = page.getByRole("button", { name: /📊 Record Counts/ }).first();
await chip.waitFor();
await chip.click();
check("AI Chat: the confirm screen says Avio runs the queries (no AI tokens)", await page.getByText(/Avio runs the queries itself/).isVisible());
check("AI Chat: no Prompt box for an action that runs queries", !(await page.getByText("Prompt", { exact: true }).count()));
await page.getByRole("button", { name: /Proceed/ }).click();
await page.waitForTimeout(150);
check("AI Chat: a 'Counting records' notice shows while it runs", await page.getByText(/Counting records on 28 objects in org-one/).isVisible());
check("AI Chat: Send box disabled while counting", await page.locator("textarea").isDisabled());
const report = page.getByTestId("record-counts-report");
await report.waitFor({ timeout: 15000 });
checkQuerySet("AI Chat");
check("AI Chat: no AI call was made for the counts", aiBody === null);
const rtext = await report.innerText();
// total = core 6335 + Obj00__c 2000 + 18 other counted custom objects x 7 = 8461 (Obj03__c failed)
check("AI Chat: headline with the aggregated total, objects counted and failures",
  /Record Counts for org-one: 8,461 records across 27 objects \(1 could not be counted\)/.test(rtext.replace(/\s+/g, " ")), rtext.slice(0, 200));
check("AI Chat: the largest objects with their shares", rtext.includes("Largest: Task 4,000 (47%), Obj00__c 2,000 (24%), Contact 1,200 (14%)"), rtext.slice(0, 400));
const rows = await report.locator("tbody tr").allInnerTexts();
check("AI Chat: one table row per object, sorted by count", rows.length === 28 && rows[0].startsWith("Task") && rows[1].startsWith("Obj00__c"), JSON.stringify(rows.slice(0, 3)));
check("AI Chat: the failed object says why, at the end", rows.at(-1).includes(FAILING) && rows.at(-1).includes("not counted") && rows.at(-1).includes("not supported"), rows.at(-1));
check("AI Chat: Send box enabled again", !(await page.locator("textarea").isDisabled()));

// A follow-up question carries the report's numbers to the AI
await page.locator("textarea").fill("Which object is growing fastest?");
await page.getByRole("button", { name: "Send" }).click();
await page.waitForTimeout(800);
const sent = aiBody?.messages || [];
const carried = sent.find((m) => m.role === "assistant" && m.content.includes("8,461 records") && m.content.includes("Task: 4,000"));
check("AI Chat: the follow-up sends the report text to the AI as context", !!carried, JSON.stringify(sent).slice(0, 300));

// A typed request (the old chip's prompt) runs the counts too, without asking the AI
await page.locator("main").getByRole("button", { name: /Clear/ }).click();   // not the debug log's Clear
queries = []; peak = 0; aiBody = null;
await page.locator("textarea").fill("List the top objects in this org by record count. Show the results in a clear table.");
await page.getByRole("button", { name: "Send" }).click();
await page.getByTestId("record-counts-report").waitFor({ timeout: 15000 });
check("AI Chat: a typed counts request runs the counts and posts the report", queries.length === 28, queries.length);
check("AI Chat: ...without an AI call", aiBody === null, JSON.stringify(aiBody).slice(0, 200));
check("AI Chat: the typed text is kept as the user's message", await page.getByText("List the top objects in this org by record count.").isVisible());

check("no page errors", errors.length === 0, errors.join(" | "));
await browser.close();
console.log("\nfailures:", fails);
process.exit(fails ? 1 : 0);
