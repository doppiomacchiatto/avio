import { chromium } from "playwright-core";
import { BROWSER } from "./browser.mjs";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const API = "http://127.0.0.1:7893";
// argv[2]: the close log fake_slow.py writes (pass the same path to both)
const LOG = process.argv[2] || path.join(os.tmpdir(), "avio-slow-closed.txt");
let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + String(detail).slice(0, 300) : "")); };
const post = (p, b) => fetch(API + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then((r) => r.json());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const closedLog = () => (fs.existsSync(LOG) ? fs.readFileSync(LOG, "utf8").split(/\r?\n/).filter(Boolean) : []);

const mk = async (label, host, model) => (await post("/api/ai/connections", { label, preset: "custom", base_url: `http://${host}:7889/v1`, model, api_key: "k", make_default: false })).connection.id;
const conn = {
  cloudSlow:   await mk("cloud slow", "127.0.0.2", "slow"),
  cloudSilent: await mk("cloud silent", "127.0.0.2", "silent"),
  cloudOk:     await mk("cloud ok", "127.0.0.2", "ok"),
  localSilent: await mk("local silent", "127.0.0.1", "silent"),
};

const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
const PANELS = {
  chat: { url: "p=chat", ph: "Ask about your org", send: "Send" },
  soql: { url: "p=soql", ph: "Ask AI about your SOQL query", send: "↑" },
  apex: { url: "p=apex", ph: "Ask AI about your Apex code", send: "↑" },
};

async function open(panel, connId) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.addInitScript(([k, v]) => localStorage.setItem(k, v), [`avio.connection.${panel}`, connId]);
  await page.goto(`http://localhost:5199/_harness/index.html?${PANELS[panel].url}`);
  await page.waitForSelector(`textarea[placeholder^="${PANELS[panel].ph}"]`);
  return { page, errors, ctx };
}
const ask = async (page, panel, text) => {
  await page.fill(`textarea[placeholder^="${PANELS[panel].ph}"]`, text);
  await page.keyboard.press("Enter");
};
const stopBtn = (page) => page.getByRole("button", { name: "■ Stop" });
const sendBtn = (page, panel) => page.getByRole("button", { name: PANELS[panel].send, exact: true });
const body = (page) => page.evaluate(() => document.body.innerText);

for (const panel of ["chat", "soql", "apex"]) {
  console.log(`\n=== ${panel} ===`);
  fs.rmSync(LOG, { force: true });

  // 1. Stop while text is streaming
  let { page, errors, ctx } = await open(panel, conn.cloudSlow);
  await ask(page, panel, "hello there");
  await page.waitForFunction(() => document.body.innerText.includes("word3 "), null, { timeout: 15000 });
  check(`${panel}: a Stop button is shown while streaming`, await stopBtn(page).isVisible());
  check(`${panel}: the Send button is replaced, not shown beside it`, (await sendBtn(page, panel).count()) === 0);
  await stopBtn(page).click();
  await page.waitForFunction(() => !/■ Stop(?!ped)/.test(document.body.innerText.replace("■ Stopped", "")), null, { timeout: 5000 });
  let t = await body(page);
  check(`${panel}: Stop button goes away`, (await stopBtn(page).count()) === 0);
  check(`${panel}: what arrived is kept`, t.includes("Here is part one.") && t.includes("word0"), t.slice(-300));
  check(`${panel}: marked "Stopped by you"`, t.includes("Stopped by you. This answer is incomplete."));
  check(`${panel}: no error text`, !/⚠ Error|Cannot reach|No reply from/.test(t), t.slice(-200));
  const lenAt = t.length; await sleep(1500);
  check(`${panel}: the text stops growing after Stop`, (await body(page)).length === lenAt);
  await page.fill(`textarea[placeholder^="${PANELS[panel].ph}"]`, "next");
  check(`${panel}: Send is available again`, await sendBtn(page, panel).isEnabled());
  let waited = 0; while (!closedLog().includes("slow") && waited < 4000) { await sleep(200); waited += 200; }
  check(`${panel}: the provider saw the connection close (it stops generating and billing)`, closedLog().includes("slow"), String(closedLog()));

  // 2. send again after a Stop works, and can be stopped again
  await ask(page, panel, "second question");
  // the first (stopped) reply already contains "word2 ": wait for the second reply's own text, or Stop
  // can land before any text has arrived and the reply gets no "Stopped by you" marker
  await page.waitForFunction(() => (document.body.innerText.match(/word2 /g) || []).length >= 2, null, { timeout: 15000 });
  check(`${panel}: sending again after a Stop streams again`, await stopBtn(page).isVisible());
  await stopBtn(page).click();
  // wait (up to 5 s) for the second "Stopped by you" marker instead of a fixed sleep
  await page.waitForFunction(() => (document.body.innerText.match(/Stopped by you/g) || []).length >= 2, null, { timeout: 5000 }).catch(() => {});
  t = await body(page);
  check(`${panel}: two stopped replies are both kept`, (t.match(/Stopped by you/g) || []).length === 2, String((t.match(/Stopped by you/g) || []).length));
  check(`${panel}: no page errors`, errors.length === 0, errors.join(" | "));
  await ctx.close();

  // 3. Stop before any text: cloud hint, then Stop leaves no empty reply
  ({ page, errors, ctx } = await open(panel, conn.cloudSilent));
  await ask(page, panel, "think hard");
  await page.waitForFunction(() => document.body.innerText.includes("Still waiting for the model"), null, { timeout: 20000 });
  t = await body(page);
  check(`${panel}: cloud wait hint says reasoning models can take a while`, t.includes("Reasoning models can take a minute or two before the first word."), t.slice(-300));
  check(`${panel}: hint does not talk about a local model loading`, !t.includes("local model can take"));
  check(`${panel}: hint tells you about Stop`, t.includes("You can press Stop to cancel."));
  await stopBtn(page).click();
  await sleep(500);
  t = await body(page);
  check(`${panel}: Stop with nothing received: no 'Stopped' note, no empty reply, panel free`,
        !t.includes("Stopped by you") && (await stopBtn(page).count()) === 0 && !t.includes("Still waiting"), t.slice(-200));
  const msgs = await page.evaluate(async () => (await import("/src/chatHistory.js")).getMessages(new URLSearchParams(location.search).get("p")));
  check(`${panel}: only the question is in the conversation`, msgs.length === 1 && msgs[0].role === "user", JSON.stringify(msgs).slice(0, 200));
  check(`${panel}: no page errors (silent)`, errors.length === 0, errors.join(" | "));
  await ctx.close();

  // 4. Local connection hint
  ({ page, errors, ctx } = await open(panel, conn.localSilent));
  await ask(page, panel, "load please");
  await page.waitForFunction(() => document.body.innerText.includes("Still waiting for the model"), null, { timeout: 20000 });
  t = await body(page);
  check(`${panel}: a local connection keeps the model-loading hint`, t.includes("local model can take a minute or two while it loads") && !t.includes("Reasoning models"), t.slice(-300));
  await stopBtn(page).click();
  await ctx.close();

  // 5. A normal reply is untouched
  ({ page, errors, ctx } = await open(panel, conn.cloudOk));
  await ask(page, panel, "hi");
  await page.waitForFunction(() => document.body.innerText.includes("And part two."), null, { timeout: 15000 });
  await sleep(500);
  t = await body(page);
  check(`${panel}: a normal reply completes with no Stop leftovers`, (await stopBtn(page).count()) === 0 && !t.includes("Stopped by you") && t.includes("Here is part one."), t.slice(-200));
  check(`${panel}: the reply still lists skills used`, t.includes("Skills used"));
  await ctx.close();
}

// ---- the timeout (config.json has chat_timeout_seconds: 10) --------------------------------------------------------
console.log("\n=== timeout ===");
{
  const { page, errors, ctx } = await open("chat", conn.cloudSilent);
  const t0 = Date.now();
  await ask(page, "chat", "anyone there");
  await page.waitForFunction(() => document.body.innerText.includes("stopped waiting"), null, { timeout: 40000 });
  const secs = (Date.now() - t0) / 1000;
  const t = await body(page);
  check("silent provider: Avio gives up on its own after about the configured 10s", secs >= 9 && secs < 25, `${secs.toFixed(1)}s`);
  check("the message names the host and the wait", t.includes("No reply from 127.0.0.2 for silent in 10 seconds, so Avio stopped waiting."), t.slice(-500));
  check("and says what to do", t.includes("chat_timeout_seconds") && t.includes("Send again"));
  check("the panel is free again (Send, no Stop)", (await stopBtn(page).count()) === 0 && await page.getByRole("button", { name: "Send", exact: true }).count() === 1);
  check("no page errors (timeout)", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

await browser.close();
console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
