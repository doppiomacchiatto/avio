// Switch Org from the AI Chat tab, in the REAL App (browser dev mode) against the real backend.
// Needs: backend on 7893 with an isolated APPDATA and no token, fake_slow.py on 7889 (its close log is
// argv[2] here), and `vite --port 5199` in frontend/. The org endpoints are mocked: no sf CLI, no real org.
import { chromium } from "playwright-core";
import { BROWSER } from "./browser.mjs";
import fs from "node:fs";

const API = "http://127.0.0.1:7893";
const APP = "http://localhost:5199/";
const LOG = process.argv[2];
let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + String(detail).slice(0, 400) : "")); };
const post = (p, b) => fetch(API + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then((r) => r.json());
const chats = () => fetch(API + "/api/chats?surface=chat").then((r) => r.json()).then((j) => j.chats);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const closed = () => (fs.existsSync(LOG) ? fs.readFileSync(LOG, "utf8").split(/\r?\n/).filter(Boolean) : []);
const U = (t) => ({ role: "user", content: t });
const A = (t) => ({ role: "assistant", content: t });

const made = [];
const mk = async (label, model) => {
  const id = (await post("/api/ai/connections", { label, preset: "custom", base_url: "http://127.0.0.2:7889/v1", model, api_key: "k", make_default: false })).connection.id;
  made.push(id);
  return id;
};
const conn = { slow: await mk("switch slow", "slow"), ok: await mk("switch ok", "ok") };

const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" };
const ORGS = [
  { alias: "org-one", username: "one@example.com", isDefault: true },
  { alias: "org-two", username: "two@example.com", isDefault: false },
];

async function open(connId) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  const state = { orgs: [...ORGS], calls: { orgs: 0, sf: 0 }, fail: false };
  // App.jsx calls Tauri's listen() for the window-close and About events; outside Tauri that rejects (dev mode only).
  page.on("pageerror", (e) => { if (!/transformCallback/.test(String(e))) errors.push(String(e)); });
  await page.addInitScript(([c]) => {
    window.__SF_BACKEND_PORT__ = 7893;
    localStorage.setItem("avio_welcome_seen_v1", "1");
    localStorage.setItem("avio.connection.chat", c);
  }, [connId]);
  await page.route(/\/api\/(sf-version|orgs)(\/.*)?(\?.*)?$/, (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const u = new URL(req.url()).pathname;
    let body = {};
    if (u === "/api/sf-version") { state.calls.sf++; body = { version: "stub" }; }
    else if (u === "/api/orgs") { state.calls.orgs++; if (state.fail) return route.fulfill({ status: 500, headers: CORS, contentType: "application/json", body: JSON.stringify({ detail: "sf CLI failed (test)" }) }); body = { orgs: state.orgs }; }
    else if (u.endsWith("/objects")) body = { objects: [] };
    else if (u.endsWith("/limits")) body = { dailyApiRequests: { used: 1, max: 100 } };
    return route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto(APP);
  await page.getByRole("button", { name: "Connect to org" }).waitFor();
  state.startupCancel = (await cancelBtn(page).count()) + (await closeBtn(page).count());
  await pickOrg(page, "org-one");
  await page.getByRole("button", { name: /AI Chat/ }).first().click();
  await page.waitForSelector('textarea[placeholder^="Ask about your org"]');
  return { page, ctx, errors, state };
}
async function pickOrg(page, alias) {
  await page.getByRole("button", { name: "Connect to org" }).waitFor();
  await page.getByText(alias, { exact: true }).click();
  await page.getByRole("button", { name: "Connect to org" }).click();
}
const switchTo = async (page, alias) => { await page.getByRole("button", { name: "Switch Org" }).click(); await pickOrg(page, alias); };
const ask = async (page, text) => { await page.fill('textarea[placeholder^="Ask about your org"]', text); await page.keyboard.press("Enter"); };
const body = (page) => page.evaluate(() => document.body.innerText);
const has = (page, text, timeout = 8000) => page.waitForFunction((t) => document.body.innerText.includes(t), text, { timeout }).then(() => true, () => false);
const stopBtn = (page) => page.getByRole("button", { name: /Stop$/ });
const restoreBtn = (page) => page.getByRole("button", { name: "Restore", exact: true });
const cancelBtn = (page) => page.getByRole("button", { name: "Cancel", exact: true });
const closeBtn = (page) => page.getByRole("button", { name: "Close without switching org" });
const connectBtn = (page) => page.getByRole("button", { name: "Connect to org" });
const OFFER = "Avio kept your last AI Chat conversation";

// ---- A. the reply has finished; an earlier offer was dismissed; Save & switch ------------------------------------
console.log("\n=== A. finished reply, Save & switch ===");
await post("/api/chats/delete-all", {});
await post("/api/chats", { surface: "chat", messages: [U("an older question"), A("an older answer")] });
await sleep(1100);                                   // saved ids have one-second resolution
{
  const { page, ctx, errors } = await open(conn.ok);
  check("A: the older saved copy is offered on open", await has(page, OFFER));
  await page.getByRole("button", { name: "Dismiss", exact: true }).click();
  check("A: Dismiss hides the offer", !(await body(page)).includes(OFFER));
  await ask(page, "first question");
  check("A: the reply arrives", await has(page, "And part two."));
  await switchTo(page, "org-two");
  check("A: the dialog asks what to do with the chat", await has(page, "Start a new AI Chat?"));
  check("A: no 'still arriving' line when nothing is streaming", !(await body(page)).includes("still arriving"));
  await page.getByRole("button", { name: "Save & switch" }).click();
  check("A: the restore offer appears without leaving the tab", await has(page, OFFER));
  let t = await body(page);
  check("A: the offer is for the chat just saved (2 messages)", /AI Chat conversation \(saved .+, 2 messages; kept until/.test(t), t.slice(0, 600));
  check("A: the chat is empty and the new org is active", t.includes("Ask me anything about your Salesforce org.") && !t.includes("first question") && t.includes("org-two"), t.slice(0, 400));
  check("A: two saved copies exist", (await chats()).length === 2, JSON.stringify(await chats()));
  await restoreBtn(page).click();
  check("A: Restore brings the conversation back", (await has(page, "first question")) && (await body(page)).includes("And part two."));
  check("A: no page errors", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

// ---- B. the reply is still arriving; Save & switch ------------------------------------------------------------------
console.log("\n=== B. reply still arriving, Save & switch ===");
await post("/api/chats/delete-all", {});
fs.rmSync(LOG, { force: true });
{
  const { page, ctx, errors } = await open(conn.slow);
  await ask(page, "second question");
  check("B: text is streaming", await has(page, "word3 ", 15000));
  await switchTo(page, "org-two");
  check("B: the dialog says the reply will be stopped", await has(page, "The reply that is still arriving will be stopped."));
  await page.getByRole("button", { name: "Save & switch" }).click();
  check("B: the restore offer appears", await has(page, OFFER));
  let t = await body(page);
  check("B: the new chat is empty", t.includes("Ask me anything about your Salesforce org.") && !t.includes("second question"), t.slice(0, 400));
  check("B: no Stop button and no 'Thinking' in the new chat", (await stopBtn(page).count()) === 0 && !t.includes("Thinking"), t.slice(-300));
  check("B: Restore is enabled", await restoreBtn(page).isEnabled());
  await sleep(1500);
  check("B: the provider saw the connection close", closed().includes("slow"), JSON.stringify(closed()));
  t = await body(page);
  check("B: nothing from the old reply lands in the new chat", !t.includes("word") && !t.includes("Here is part one."), t.slice(0, 400));
  const saved = await chats();
  check("B: one saved copy with the question and the partial answer", saved.length === 1 && saved[0].count === 2, JSON.stringify(saved));
  await restoreBtn(page).click();
  check("B: Restore brings back the question and what had arrived", (await has(page, "second question")) && (await body(page)).includes("Here is part one."));
  const before = (await body(page)).length; await sleep(1200);
  check("B: the restored text does not grow", (await body(page)).length === before);
  await ask(page, "third question");
  check("B: a new message can be sent afterwards", await has(page, "third question") && await has(page, "Here is part one.", 8000));
  if (await stopBtn(page).count()) await stopBtn(page).click();
  check("B: no page errors", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

// ---- C. the reply is still arriving; Discard & switch ---------------------------------------------------------------
console.log("\n=== C. reply still arriving, Discard & switch ===");
await post("/api/chats/delete-all", {});
fs.rmSync(LOG, { force: true });
{
  const { page, ctx, errors } = await open(conn.slow);
  await ask(page, "fourth question");
  check("C: text is streaming", await has(page, "word3 ", 15000));
  await switchTo(page, "org-two");
  await has(page, "Start a new AI Chat?");
  await page.getByRole("button", { name: "Discard & switch" }).click();
  check("C: the new org is active with an empty chat", await has(page, "Ask me anything about your Salesforce org."));
  await sleep(1500);
  const t = await body(page);
  check("C: nothing was saved and nothing is offered", (await chats()).length === 0 && !t.includes(OFFER), t.slice(0, 300));
  check("C: the provider saw the connection close", closed().includes("slow"), JSON.stringify(closed()));
  check("C: no Stop button, no stray text", (await stopBtn(page).count()) === 0 && !t.includes("word") && !t.includes("Thinking"), t.slice(-300));
  check("C: no page errors", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

// ---- D. the reply is still arriving; Cancel ----------------------------------------------------------------------------
console.log("\n=== D. reply still arriving, Cancel ===");
fs.rmSync(LOG, { force: true });
{
  const { page, ctx, errors } = await open(conn.slow);
  await ask(page, "fifth question");
  check("D: text is streaming", await has(page, "word3 ", 15000));
  await switchTo(page, "org-two");
  await has(page, "Start a new AI Chat?");
  await cancelBtn(page).last().click();              // the dialog's Cancel (the picker behind it has one too)
  const n1 = (await body(page)).length; await sleep(1200); const t = await body(page);
  check("D: the reply keeps arriving", t.length > n1 && (await stopBtn(page).count()) === 1);
  check("D: the provider connection is still open", !closed().includes("slow"), JSON.stringify(closed()));
  await pickOrg(page, "org-one");                    // the picker is still open behind the dialog: stay on the same org
  check("D: staying on the same org keeps the chat", (await body(page)).includes("fifth question"));
  await stopBtn(page).click();
  check("D: no page errors", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

// ---- E. Switch Org uses the org list loaded at startup (no second `sf org list`) --------------------------------------
console.log("\n=== E. Switch Org reuses the org list ===");
{
  const { page, ctx, errors, state } = await open(conn.ok);
  check("E: startup asked the CLI once", state.calls.orgs === 1 && state.calls.sf === 1, JSON.stringify(state.calls));
  await page.getByRole("button", { name: "Switch Org" }).click();
  await page.getByRole("button", { name: "Connect to org" }).waitFor({ timeout: 1000 });
  let t = await body(page);
  check("E: the list is shown at once", t.includes("org-one") && t.includes("org-two") && !t.includes("Loading orgs") && !t.includes("Starting data services"), t.slice(0, 300));
  check("E: Connect is enabled with the default org chosen", await page.getByRole("button", { name: "Connect to org" }).isEnabled());
  await sleep(1500);
  check("E: no CLI call was made for the switch", state.calls.orgs === 1 && state.calls.sf === 1, JSON.stringify(state.calls));

  state.orgs.push({ alias: "org-three", username: "three@example.com", isDefault: false });
  await page.getByText("org-two", { exact: true }).click();
  await page.getByRole("button", { name: /Refresh org list/ }).click();
  check("E: Refresh asks the CLI again and shows the new org", (await has(page, "org-three")) && state.calls.orgs === 2 && state.calls.sf === 1, JSON.stringify(state.calls));
  await pickOrg(page, "org-two");
  check("E: the selection survived the refresh and the switch works", await has(page, "two@example.com") || (await body(page)).includes("org-two"));

  await page.getByRole("button", { name: "Switch Org" }).click();
  await page.getByRole("button", { name: "Connect to org" }).waitFor({ timeout: 1000 });
  check("E: the refreshed list is the one kept", (await body(page)).includes("org-three") && state.calls.orgs === 2);
  state.fail = true;
  await page.getByRole("button", { name: /Refresh org list/ }).click();
  check("E: a failed refresh says so", await has(page, "Could not refresh"));
  t = await body(page);
  check("E: a failed refresh keeps the list", t.includes("org-one") && t.includes("org-three") && await page.getByRole("button", { name: "Connect to org" }).isEnabled(), t.slice(0, 300));
  state.fail = false;
  await pickOrg(page, "org-three");
  await page.getByRole("button", { name: "Switch Org" }).click();
  await page.getByRole("button", { name: "Connect to org" }).waitFor({ timeout: 1000 });
  check("E: the list is still kept after a failed refresh", (await body(page)).includes("org-two") && state.calls.orgs === 3, JSON.stringify(state.calls));
  check("E: no page errors", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

// ---- F. the picker can be closed without switching once an org is connected ---------------------------------------------
console.log("\n=== F. cancel the org picker ===");
await post("/api/chats/delete-all", {});
{
  const { page, ctx, errors, state } = await open(conn.ok);
  check("F: at startup there is no Cancel or close button", state.startupCancel === 0, String(state.startupCancel));
  await ask(page, "sixth question");
  check("F: the reply arrives", await has(page, "And part two."));
  await page.getByRole("button", { name: "Switch Org" }).click();
  await connectBtn(page).waitFor({ timeout: 1000 });
  check("F: Switch Org offers Cancel and a close button", (await cancelBtn(page).count()) === 1 && (await closeBtn(page).count()) === 1);
  await page.getByText("org-two", { exact: true }).click();
  await page.getByRole("button", { name: /Refresh org list/ }).click();
  await page.getByRole("button", { name: /Refresh org list/ }).waitFor();
  await cancelBtn(page).click();
  let t = await body(page);
  check("F: Cancel closes the picker", (await connectBtn(page).count()) === 0);
  check("F: the org is unchanged and the chat is untouched", t.includes("org-one") && !t.includes("Start a new AI Chat?") && t.includes("sixth question") && t.includes("And part two."), t.slice(0, 300));
  await page.getByRole("button", { name: "Switch Org" }).click();
  await connectBtn(page).waitFor({ timeout: 1000 });
  await closeBtn(page).click();
  check("F: the close button closes the picker too", (await connectBtn(page).count()) === 0 && (await body(page)).includes("sixth question"));
  await page.getByRole("button", { name: "Switch Org" }).click();
  await page.getByRole("button", { name: /Log in to another org/ }).click();
  await has(page, "Log in with browser");
  check("F: no Cancel or close button on the login panel (it has Back)", (await cancelBtn(page).count()) === 0 && (await closeBtn(page).count()) === 0);
  check("F: no page errors", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

await browser.close();
await post("/api/chats/delete-all", {});
for (const id of made) await post("/api/ai/connections/delete", { id });
console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
