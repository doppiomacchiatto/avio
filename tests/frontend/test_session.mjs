import { pathToFileURL, fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const root = fileURLToPath(new URL("../../frontend/src/", import.meta.url));
const req = createRequire(pathToFileURL(root + "x.js"));
const React = req("react");
const { renderToString } = req("react-dom/server");
const { getSession, setSession, clearSession, subscribeSession, useSessionState } =
  await import(pathToFileURL(root + "sessionStore.js").href);

let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + detail.slice(0, 300) : "")); };

// ---- the store ---------------------------------------------------------------------------------------
const a = getSession("t.list", []);
check("first read returns the initial value", Array.isArray(a) && a.length === 0);
check("later reads return the SAME reference (stable for React)", getSession("t.list", []) === a);
check("an initial function runs once", (() => { let n = 0; const f = () => (n++, "v"); getSession("t.fn", f); getSession("t.fn", f); return n === 1; })());
setSession("t.list", (prev) => [...prev, "one"]);
setSession("t.list", (prev) => [...prev, "two"]);
check("updaters see the latest value, in order", JSON.stringify(getSession("t.list", [])) === '["one","two"]');
let calls = 0; const off = subscribeSession(() => calls++);
setSession("t.list", getSession("t.list", []));
check("setting the same value does not notify", calls === 0);
setSession("t.val", 5); check("a change notifies subscribers", calls === 1);
off(); setSession("t.val", 6); check("unsubscribed listeners are not called", calls === 1);
setSession("apex.x", 1); setSession("soql.x", 2);
check("keys are independent (apex / soql / chat)", getSession("apex.x", 0) === 1 && getSession("soql.x", 0) === 2);
clearSession("apex.");
check("clearSession(prefix) forgets only that prefix", getSession("apex.x", "gone") === "gone" && getSession("soql.x", 0) === 2);
setSession("never.initialised", (p) => (p ?? 0) + 1);
check("an updater on an unset key starts from undefined", getSession("never.initialised", 99) === 1);

// ---- the user's scenario: leave the tab and come back --------------------------------------------------
function Panel() {
  const [messages] = useSessionState("apex.ai.messages", []);
  const [open] = useSessionState("apex.ai.open", false);
  const [input] = useSessionState("apex.ai.input", "");
  return React.createElement("div", null, `open=${open};n=${messages.length};input=${input};` + messages.map((m) => m.role + ":" + m.content).join("|"));
}
const render = () => renderToString(React.createElement(Panel)).replace(/<[^>]+>/g, "");

clearSession("apex.");
check("first visit: empty, panel closed", render() === "open=false;n=0;input=;", render());
setSession("apex.ai.open", true);
setSession("apex.ai.input", "draft question");
setSession("apex.ai.messages", (m) => [...m, { role: "user", content: "write a test" }]);
setSession("apex.ai.messages", (m) => [...m, { role: "assistant", content: "here is a test class" }]);
// the tab is unmounted here (a different tab is shown) and mounted again later:
check("coming back: the panel is still open, the history and the draft are there",
  render() === "open=true;n=2;input=draft question;user:write a test|assistant:here is a test class", render());

// a reply that finishes while the user is on another tab (no component mounted)
setSession("apex.ai.messages", (m) => [...m, { role: "assistant", content: "finished while away" }]);
check("a reply that arrives while another tab is showing is kept", render().includes("n=3") && render().includes("finished while away"), render());

check("the Apex, SOQL and AI Chat histories do not mix",
  (setSession("soql.ai.messages", [{ role: "user", content: "q" }]), setSession("chat.messages", []),
   getSession("apex.ai.messages", []).length === 3 && getSession("soql.ai.messages", []).length === 1 && getSession("chat.messages", [1]).length === 0));

check("Clear (empty list) empties the history for the next visit", (setSession("apex.ai.messages", []), render().includes("n=0")));

console.log("\nfailures:", fails);
process.exit(fails ? 1 : 0);
