// The e2e harness page (see tests/README.md). Served at /_harness/index.html by vite.harness.config.mjs, with the
// app's own frontend/ as Vite's root, so /src/... below are the real modules (and the same instances the tests
// import from the page), styled by the app's real index.css.
//   ?p=chat|soql|apex|fls|profiles|rest   the real AI Chat, SOQL Runner, Apex Runner, FLS Explorer, Profiles & PermSets
//                       or REST Explorer page, AI panel open, no org (e2e_stop.mjs)
//   no ?p               the real AiHistoryStrip for the Apex surface, plus #msgs (the conversation as JSON) and
//                       #add / #clear buttons that change it the way a panel does (e2e.mjs)
import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import "/src/index.css";
import ClaudeChat from "/src/pages/ClaudeChat.jsx";
import SoqlRunner from "/src/pages/SoqlRunner.jsx";
import ApexRunner from "/src/pages/ApexRunner.jsx";
import FlsExplorer from "/src/pages/FlsExplorer.jsx";
import ProfilesExplorer from "/src/pages/ProfilesExplorer.jsx";
import RestExplorer from "/src/pages/RestExplorer.jsx";
import AiHistoryStrip from "/src/components/AiHistoryStrip.jsx";
import { setSession, useSessionState } from "/src/sessionStore.js";
import { SURFACES } from "/src/chatHistory.js";

const p = new URLSearchParams(location.search).get("p");

function Panel() {
  const [ctx, setCtx] = useState({ objects: [], objectsLoaded: false, objectsLoading: false });
  const props = { org: null, ctx, setCtx, loadObjects: () => {}, onApiCall: () => {} };
  const Page = { chat: ClaudeChat, soql: SoqlRunner, apex: ApexRunner, fls: FlsExplorer, profiles: ProfilesExplorer, rest: RestExplorer }[p];
  return (
    <div className="h-screen flex flex-col bg-white dark:bg-gray-900">
      <Page {...props} />
    </div>
  );
}

function StripHarness() {
  const surface = "apex";
  const [messages, setMessages] = useSessionState(SURFACES[surface].key, []);
  return (
    <div className="h-screen flex flex-col bg-slate-900 text-slate-200">
      <AiHistoryStrip surface={surface} />
      <div className="p-3 flex gap-2 text-xs">
        <button id="add" className="px-2 py-1 rounded bg-slate-700"
          onClick={() => setMessages((m) => [...m, { role: "user", content: `added ${m.length + 1}` }])}>add message</button>
        <button id="clear" className="px-2 py-1 rounded bg-slate-700" onClick={() => setMessages([])}>clear</button>
      </div>
      <pre id="msgs" className="p-3 text-xs whitespace-pre-wrap">{JSON.stringify(messages)}</pre>
    </div>
  );
}

if (p && p !== "chat") setSession(`${p}.ai.open`, true);
ReactDOM.createRoot(document.getElementById("root")).render(p ? <Panel /> : <StripHarness />);
