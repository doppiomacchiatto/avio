import { pathToFileURL, fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../../frontend/src/", import.meta.url));
const H = await import(pathToFileURL(root + "chatHistory.js").href);
const S = await import(pathToFileURL(root + "sessionStore.js").href);

let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + String(detail).slice(0, 300) : "")); };
const U = (t) => ({ role: "user", content: t });
const A = (t, extra = {}) => ({ role: "assistant", content: t, ...extra });

// ---- cleanMessages --------------------------------------------------------------------------------------
const c = H.cleanMessages([U("hi"), A("yo", { skills: ["Apex Generate", 5, "", "x".repeat(300)], extra: 1 }),
  { role: "system", content: "no" }, { role: "user", content: 5 }, { role: "user", content: "  " },
  A("notice", { system: true }), "junk", null, A(""), U("<img src=x onerror=alert(1)>")]);
check("keeps only valid user/assistant text", c.map((m) => m.role).join() === "user,assistant,user", JSON.stringify(c));
check("unknown fields dropped", Object.keys(c[1]).sort().join() === "content,role,skills", JSON.stringify(c[1]));
check("skills filtered, long names cut", JSON.stringify(c[1].skills) === JSON.stringify(["Apex Generate", "x".repeat(100)]));
check("HTML stays plain text", c[2].content === "<img src=x onerror=alert(1)>");
check("user messages carry no skills", H.cleanMessages([{ ...U("a"), skills: ["x"] }])[0].skills === undefined);
check("non-array gives empty", H.cleanMessages("x").length === 0 && H.cleanMessages(null).length === 0 && H.cleanMessages({}).length === 0);
check("cleaning does not mutate its input", (() => { const m = [{ ...A("x"), junk: 1 }]; H.cleanMessages(m); return m[0].junk === 1; })());

// ---- titles, tokens -------------------------------------------------------------------------------------
check("title: first user message", H.makeTitle([A("a"), U("Write a test"), U("later")]) === "Write a test");
check("title: cut at 60 with ...", (() => { const t = H.makeTitle([U("word ".repeat(40))]); return t.length === 63 && t.endsWith("..."); })());
check("title: whitespace collapsed; explicit title wins", H.makeTitle([U("a\n\n  b")]) === "a b" && H.makeTitle([U("x")], " My  t ") === "My t");
check("tokens ~ chars / 4, rounded up, ignoring dropped entries", H.estimateTokens([U("a".repeat(10)), A("b".repeat(11)), A("c", { system: true })]) === 6);

// ---- serialize + parse round trip ------------------------------------------------------------------------
const msgs = [U("Write a test class"), A("```apex\nclass T {}\n```", { skills: ["Apex Test Generate"] })];
const file = H.serializeChat("apex", [...msgs, A("notice", { system: true })], { appVersion: "1.0.2", now: new Date("2026-11-16T09:30:00Z") });
check("serialize: version, surface, time, app version, title", file.avio_chat === 1 && file.surface === "apex" && file.saved_at === "2026-11-16T09:30:00.000Z"
  && file.app_version === "1.0.2" && file.title === "Write a test class", JSON.stringify(file));
check("serialize: UI notices left out", file.messages.length === 2);
check("serialize: no connection, key or URL fields", !["connection", "api_key", "base_url", "url"].some((k) => k in file));
const back = H.parseChatFile(JSON.stringify(file));
check("round trip keeps messages exactly", back.ok && JSON.stringify(back.chat.messages) === JSON.stringify(msgs) && back.chat.surface === "apex" && back.chat.ignored === 0, JSON.stringify(back));
check("a UTF-8 BOM is tolerated", H.parseChatFile("\uFEFF" + JSON.stringify(file)).ok);

// ---- parse: hostile / broken files -----------------------------------------------------------------------
const bad = (name, text, re) => { const r = H.parseChatFile(text); check(name, !r.ok && (!re || re.test(r.error)), JSON.stringify(r)); };
bad("not JSON", "hello", /not valid JSON/);
bad("empty string", "", /not valid JSON/);
bad("non-string input", null, /read as text/);
bad("JSON but not an object", "[1,2]", /not an Avio/);
bad("a different JSON file (package.json-like)", JSON.stringify({ name: "x", version: "1" }), /not an Avio/);
bad("version as a string", JSON.stringify({ avio_chat: "1", messages: [U("x")] }), /not an Avio/);
bad("a newer version", JSON.stringify({ avio_chat: 2, messages: [U("x")] }), /newer version/);
bad("version 0", JSON.stringify({ avio_chat: 0, messages: [U("x")] }), /old format/);
bad("no messages array", JSON.stringify({ avio_chat: 1 }), /no messages/);
bad("messages not an array", JSON.stringify({ avio_chat: 1, messages: "x" }), /no messages/);
bad("all messages invalid", JSON.stringify({ avio_chat: 1, messages: [{ role: "system", content: "x" }, { role: "user", content: 5 }] }), /no messages Avio can use/);
bad("over 500 messages", JSON.stringify({ avio_chat: 1, messages: Array.from({ length: 501 }, (_, i) => U("m" + i)) }), /more than 500/);
bad("over 2M characters", JSON.stringify({ avio_chat: 1, messages: [U("a".repeat(1_100_000)), A("b".repeat(1_100_000))] }), /too long/);
bad("a huge file is refused before parsing", "x".repeat(5_000_001), /too large/);
const ok500 = H.parseChatFile(JSON.stringify({ avio_chat: 1, messages: Array.from({ length: 500 }, (_, i) => U("m" + i)) }));
check("exactly 500 messages loads", ok500.ok && ok500.chat.messages.length === 500);
const mixed = H.parseChatFile(JSON.stringify({ avio_chat: 1, surface: "evil", title: 5, saved_at: 7, messages: [U("keep"), { role: "tool", content: "x" }, A("also", { __proto__: { admin: true }, x: 1 })] }));
check("bad entries are ignored and counted, odd surface/title/saved_at tolerated",
  mixed.ok && mixed.chat.messages.length === 2 && mixed.chat.ignored === 1 && mixed.chat.surface === null && mixed.chat.title === "keep" && mixed.chat.savedAt === "", JSON.stringify(mixed));
const proto = H.parseChatFile('{"avio_chat":1,"messages":[{"role":"user","content":"x","__proto__":{"polluted":true}}],"__proto__":{"polluted":true}}');
check("__proto__ keys do not pollute anything", proto.ok && ({}).polluted === undefined && proto.chat.messages[0].polluted === undefined);
check("a surface that is an Object.prototype name is not accepted", H.parseChatFile(JSON.stringify({ avio_chat: 1, surface: "toString", messages: [U("x")] })).chat.surface === null
  && H.parseChatFile(JSON.stringify({ avio_chat: 1, surface: "constructor", messages: [U("x")] })).chat.surface === null);

// ---- markdown -------------------------------------------------------------------------------------------
const md = H.toMarkdown(file);
check("markdown: title, headings, code fence preserved", md.startsWith("# Write a test class") && md.includes("## You\n\nWrite a test class") && md.includes("## AI\n\n```apex\nclass T {}\n```"), md);
check("markdown: skills and surface noted", md.includes("_Skills used: Apex Test Generate_") && md.includes("Apex Runner"));

// ---- merge ----------------------------------------------------------------------------------------------
check("replace drops the current conversation", H.mergeMessages([U("old")], [U("new")], "replace").length === 1);
check("append adds after the current one", H.mergeMessages([U("old"), A("a")], [U("new")], "append").map((m) => m.content).join() === "old,a,new");
check("append is capped at 500, newest kept", (() => { const m = H.mergeMessages(Array.from({ length: 400 }, (_, i) => U("o" + i)), Array.from({ length: 200 }, (_, i) => U("n" + i)), "append"); return m.length === 500 && m.at(-1).content === "n199" && m[0].content === "o100"; })());
check("file name is avio-<surface>-<stamp>.<ext>", H.defaultFileName("soql", "md", new Date(2026, 10, 16, 9, 5)) === "avio-soql-20261116-0905.md");

// ---- unsaved tracking --------------------------------------------------------------------------------------
const key = (s) => H.SURFACES[s].key;
H.forgetSaved();
check("nothing unsaved at the start", H.unsavedChats().length === 0 && !H.hasUnsavedChats());
S.setSession(key("apex"), [U("q")]);
check("a conversation with messages is unsaved", JSON.stringify(H.unsavedChats()) === JSON.stringify([{ surface: "apex", label: "Apex Runner", count: 1 }]), JSON.stringify(H.unsavedChats()));
S.setSession(key("chat"), (m) => [...(m || []), U("a"), A("b")]);
check("several surfaces reported with counts", H.unsavedChats().map((u) => u.surface + ":" + u.count).join() === "apex:1,chat:2");
H.markSaved("apex");
check("markSaved clears just that surface", H.unsavedChats().map((u) => u.surface).join() === "chat");
S.setSession(key("apex"), (m) => [...m, A("reply")]);
check("a new message makes it unsaved again", H.unsavedChats().map((u) => u.surface).join() === "apex,chat");
S.setSession(key("soql"), [A("notice", { system: true }), { role: "assistant", content: "" }]);
check("only UI notices / empty placeholders: nothing to save", !H.unsavedChats().some((u) => u.surface === "soql"));
S.setSession(key("chat"), []);
check("an empty conversation is not unsaved", !H.unsavedChats().some((u) => u.surface === "chat"));

// restore / load
H.setMessages("soql", [U("restored")], { markAsSaved: true });
check("restoring marks it saved", !H.unsavedChats().some((u) => u.surface === "soql") && H.getMessages("soql")[0].content === "restored");
H.loadIntoSurface("soql", [U("from file")], "replace");
check("file load (replace) leaves nothing unsaved", !H.unsavedChats().some((u) => u.surface === "soql") && H.getMessages("soql").length === 1);
H.loadIntoSurface("soql", [A("more")], "append");
check("append makes it unsaved (the combination was never saved)", H.unsavedChats().some((u) => u.surface === "soql") && H.getMessages("soql").length === 2);
H.resetSurface("soql");
check("resetSurface empties it", H.getMessages("soql").length === 0 && !H.unsavedChats().some((u) => u.surface === "soql"));

// ---- saveUnsavedToApp -------------------------------------------------------------------------------------
H.forgetSaved();
S.setSession(key("apex"), [U("q"), A("a", { skills: ["S"] }), A("notice", { system: true })]);
S.setSession(key("chat"), [U("c")]);
const calls = [];
let r = await H.saveUnsavedToApp(async (path, body) => { calls.push([path, body]); return { id: "x" }; });
check("posts each unsaved surface to /api/chats", calls.length === 2 && calls.every(([p]) => p === "/api/chats") && calls.map(([, b]) => b.surface).join() === "apex,chat");
check("sends cleaned messages only (no UI notices)", calls[0][1].messages.length === 2 && JSON.stringify(calls[0][1]).includes("skills"));
check("reports what saved and marks it saved", r.saved.length === 2 && r.failed.length === 0 && !H.hasUnsavedChats());
S.setSession(key("apex"), (m) => [...m, U("next")]);
S.setSession(key("chat"), (m) => [...m, U("next")]);
r = await H.saveUnsavedToApp(async (path, body) => { if (body.surface === "apex") throw new Error("disk full"); return {}; });
check("a failure is reported per surface and the rest still saved", r.saved.map((s) => s.surface).join() === "chat" && r.failed.length === 1 && r.failed[0].surface === "apex" && /disk full/.test(r.failed[0].error), JSON.stringify(r));
check("a failed surface stays unsaved", H.unsavedChats().map((u) => u.surface).join() === "apex");
r = await H.saveUnsavedToApp(async () => { throw "plain string"; });
check("non-Error rejections are reported too", r.failed.length === 1 && r.failed[0].error === "plain string");

// `only` limits the save to some surfaces
H.forgetSaved();
S.setSession(key("apex"), [U("q")]); S.setSession(key("chat"), [U("c")]); S.setSession(key("soql"), []);
const only = [];
r = await H.saveUnsavedToApp(async (p, b) => { only.push(b.surface); return {}; }, ["chat"]);
check("saveUnsavedToApp(post, ['chat']) saves only AI Chat", only.join() === "chat" && r.saved.length === 1 && H.unsavedChats().map((u) => u.surface).join() === "apex");

// ---- picked file names -------------------------------------------------------------------------------------
check("a .md export is explained, not 'not valid JSON'", /cannot load back/.test(H.checkFileName("avio-apex-20261116-2058.md") || "") && /save it as \.json/.test(H.checkFileName("x.md")));
check("also .markdown, .txt and upper case", ["a.markdown", "a.txt", "A.MD"].every((n) => H.checkFileName(n)));
check(".json (any case) is allowed", H.checkFileName("a.json") === null && H.checkFileName("A.JSON") === null);
check("odd names do not crash", H.checkFileName("") === null && H.checkFileName(null) === null && H.checkFileName(undefined) === null && H.checkFileName("notes.md.json") === null);

console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
