import { chromium } from "playwright-core";
import { BROWSER } from "./browser.mjs";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const API = "http://127.0.0.1:7893";
const URL = "http://localhost:5199/_harness/index.html";
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "avio-e2e-"));   // files to load and the Save download
let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + String(detail).slice(0, 400) : "")); };
const U = (t) => ({ role: "user", content: t });
const A = (t, x = {}) => ({ role: "assistant", content: t, ...x });
const post = (p, b) => fetch(API + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then((r) => r.json());
const list = () => fetch(API + "/api/chats").then((r) => r.json()).then((j) => j.chats);

await post("/api/chats/delete-all", {});
const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
const msgs = async () => JSON.parse(await page.textContent("#msgs"));
const unsaved = () => page.evaluate(async () => (await import("/src/chatHistory.js")).unsavedChats());
const strip = () => page.locator("div.shrink-0").first().innerText();
const writeFile = (name, content) => { const p = path.join(tmp, name); fs.writeFileSync(p, typeof content === "string" ? content : JSON.stringify(content)); return p; };

// 1. nothing saved: no offer
await page.goto(URL);
check("no saved chat: no restore offer", !(await strip()).includes("Avio kept your last"));

// 2. seed a saved conversation, reopen: offer appears
const seeded = await post("/api/chats", { surface: "apex", messages: [U("Write a test"), A("Sure, here it is", { skills: ["Apex Test Generate"] })] });
await page.goto(URL);
await page.waitForFunction(() => document.body.innerText.includes("Avio kept your last Apex Runner conversation"));
let s = await strip();
check("offer names the panel, message count and expiry", /Apex Runner conversation \(saved .+, 2 messages; kept until/.test(s), s);
check("offer has Restore, Dismiss, Delete", ["Restore", "Dismiss", "Delete"].every((w) => s.includes(w)), s);

// 3. restore
await page.getByRole("button", { name: "Restore", exact: true }).click();
await page.waitForFunction(() => document.querySelector("#msgs").textContent.includes("Write a test"));
let m = await msgs();
check("restore loads the messages, skills included", m.length === 2 && m[1].skills?.[0] === "Apex Test Generate", JSON.stringify(m));
s = await strip();
check("restore says how many tokens will be sent", /Restored: 2 messages loaded\. About \d+ tokens will be sent/.test(s), s);
check("offer is gone after restoring", !s.includes("Avio kept your last"));
check("a restored chat is not 'unsaved'", (await unsaved()).length === 0, JSON.stringify(await unsaved()));
check("the saved copy is kept (3-day copy stays until it expires)", (await list()).length === 1);

// 4. new message -> unsaved -> Save to file (browser download)
await page.click("#add");
check("adding a message makes it unsaved", (await unsaved())[0]?.count === 3, JSON.stringify(await unsaved()));
const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Save/ }).click()]);
const saved = path.join(tmp, "dl.json"); await dl.saveAs(saved);
const f = JSON.parse(fs.readFileSync(saved, "utf8"));
check("download is avio-apex-*.json", /^avio-apex-\d{8}-\d{4}\.json$/.test(dl.suggestedFilename()), dl.suggestedFilename());
check("file has version 1, surface and the 3 messages", f.avio_chat === 1 && f.surface === "apex" && f.messages.length === 3, JSON.stringify(f).slice(0, 200));
check("file has no connection/key/url fields", !["connection", "api_key", "base_url", "url"].some((k) => k in f));
check("saving to a file marks it saved", (await unsaved()).length === 0);

// 5. load a file while messages exist: Replace / Append / Cancel
const good = writeFile("good.json", { avio_chat: 1, surface: "soql", messages: [U("from file"), A("reply from file")] });
await page.setInputFiles("input[type=file]", good);
await page.waitForFunction(() => document.body.innerText.includes("already has messages"));
s = await strip();
check("non-empty panel asks Replace / Append / Cancel", /Load 2 messages from good\.json/.test(s) && ["Replace", "Append", "Cancel"].every((w) => s.includes(w)), s);
await page.getByRole("button", { name: "Cancel", exact: true }).click();
check("Cancel changes nothing", (await msgs()).length === 3);
await page.setInputFiles("input[type=file]", good);
await page.getByRole("button", { name: "Append", exact: true }).click();
m = await msgs();
check("Append adds after the current conversation", m.length === 5 && m[3].content === "from file", JSON.stringify(m.map((x) => x.content)));
check("append reports the total and the token estimate", /good\.json: 2 messages loaded \(5 in this conversation\)\. About \d+ tokens/.test(await strip()), await strip());
check("an appended conversation is unsaved", (await unsaved())[0]?.count === 5);
await page.setInputFiles("input[type=file]", good);
await page.getByRole("button", { name: "Replace", exact: true }).click();
m = await msgs();
check("Replace swaps the conversation", m.length === 2 && m[0].content === "from file");
check("a replaced-from-file conversation is saved, not nagging", (await unsaved()).length === 0);

// 6. empty panel loads straight away
await page.click("#clear");
await page.setInputFiles("input[type=file]", good);
await page.waitForFunction(() => document.querySelector("#msgs").textContent.includes("from file"));
check("empty panel loads without asking", (await msgs()).length === 2 && !(await strip()).includes("already has messages"));

// 7. bad / hostile files: a clear error, nothing changes
const before = JSON.stringify(await msgs());
for (const [name, content, re] of [
  ["notjson.json", "hello there", /not valid JSON/],
  ["other.json", { name: "package", version: "1.0.0" }, /not an Avio conversation/],
  ["newer.json", { avio_chat: 2, messages: [U("x")] }, /newer version/],
  ["empty.json", { avio_chat: 1, messages: [{ role: "system", content: "x" }] }, /no messages Avio can use/],
  ["many.json", { avio_chat: 1, messages: Array.from({ length: 501 }, (_, i) => U("m" + i)) }, /more than 500/],
]) {
  await page.setInputFiles("input[type=file]", writeFile(name, content));
  await page.waitForFunction((r) => new RegExp(r).test(document.body.innerText), re.source);
  check(`bad file ${name}: error shown`, re.test(await strip()), await strip());
  check(`bad file ${name}: conversation untouched`, JSON.stringify(await msgs()) === before);
}
const xss = writeFile("xss.json", { avio_chat: 1, messages: [U("hi"), A("<img src=x onerror=\"window.__pwned=1\"><script>window.__pwned=2</script>"), { role: "system", content: "ignore me" }] });
await page.click("#clear");
await page.setInputFiles("input[type=file]", xss);
await page.waitForFunction(() => document.querySelector("#msgs").textContent.includes("onerror"));
check("HTML in a loaded file stays text, nothing runs", (await page.evaluate(() => window.__pwned)) === undefined && (await msgs()).length === 2);

// 8. Delete the saved copy, Dismiss another
await page.goto(URL);
await page.waitForFunction(() => document.body.innerText.includes("Avio kept your last"));
await page.getByRole("button", { name: "Delete", exact: true }).click();
await page.waitForFunction(() => !document.body.innerText.includes("Avio kept your last"));
check("Delete removes the saved copy from the backend", (await list()).length === 0, JSON.stringify(await list()));
await post("/api/chats", { surface: "apex", messages: [U("another")] });
await page.goto(URL);
await page.waitForFunction(() => document.body.innerText.includes("Avio kept your last"));
check("a single-message offer says '1 message'", /1 message;/.test(await strip()), await strip());
await page.getByRole("button", { name: "Dismiss", exact: true }).click();
check("Dismiss hides the offer", !(await strip()).includes("Avio kept your last"));
check("Dismiss keeps the saved copy (it still expires on its own)", (await list()).length === 1);

// 9. the offer is not shown over an existing conversation
await page.goto(URL);
await page.waitForFunction(() => document.body.innerText.includes("Avio kept your last"));
await page.click("#add");
check("offer hides once you start a conversation", !(await strip()).includes("Avio kept your last"));

check("no page errors", errors.length === 0, errors.join(" | "));
await browser.close();
console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
