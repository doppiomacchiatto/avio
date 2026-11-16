/**
 * OpenCode AI chat page — full RAG pipeline:
 * fuzzy object matching, field loading, SOQL generation.
 */
import { useState, useRef, useEffect } from "react";
import { api, apiStream } from "../api/client";
import { CONTINUE_PROMPT } from "../aiBlocks";
import { SlowHint, TruncatedNotice, SkillsUsed } from "../components/AiNotices";
import ConnectionPicker from "../components/ConnectionPicker";
import { useConnectionChoice } from "../connections";
import { buildChatSystem } from "../chatSystem";
import Spinner from "../components/Spinner";
import {
  HEALTH_CHECKS, CHECK_CATEGORIES, CATEGORY_ICONS,
  STATUS_ICON, STATUS_COLOR,
} from "../data/healthChecks";

function OrgHealthCheck({ org, onClose }) {
  // "preflight" → "running" → "done"
  const [phase,    setPhase]    = useState("preflight");
  // results[id] = { status, detail } | undefined = not run yet | null = running
  const [results,  setResults]  = useState({});
  const [current,  setCurrent]  = useState(null);  // { idx, label }
  const [done,     setDone]     = useState(false);
  // Hooks must stay above the preflight early return (React error #310)
  const [expanded,     setExpanded]     = useState({});   // { [id]: true }
  const [drillRows,    setDrillRows]    = useState({});   // { [id]: rows[] | "loading" | "error" }
  const cancelRef = useRef(false);

  function startChecks() {
    cancelRef.current = false;
    setPhase("running");
    runAll();
  }

  async function runAll() {
    for (let i = 0; i < HEALTH_CHECKS.length; i++) {
      if (cancelRef.current) break;
      const chk = HEALTH_CHECKS[i];
      setCurrent({ idx: i, label: chk.label });
      setResults(r => ({ ...r, [chk.id]: null })); // null = running
      try {
        const result = await chk.run(org.alias, api);
        if (!cancelRef.current)
          setResults(r => ({ ...r, [chk.id]: result }));
      } catch (e) {
        if (!cancelRef.current)
          setResults(r => ({ ...r, [chk.id]: { status: "fail", detail: e.message } }));
      }
    }
    if (!cancelRef.current) { setCurrent(null); setDone(true); }
  }

  const total   = HEALTH_CHECKS.length;
  const checked = Object.values(results).filter(r => r !== null && r !== undefined).length;
  const fails   = Object.values(results).filter(r => r?.status === "fail").length;
  const warns   = Object.values(results).filter(r => r?.status === "warn").length;

  // ── Preflight screen ───────────────────────────────────────────────────────
  if (phase === "preflight") return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-gray-900">
      <div className="shrink-0 flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-800 border-b border-slate-200 dark:border-gray-700">
        <span className="text-base font-bold text-slate-900 dark:text-gray-100">🏥 Org Health Check</span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-800 dark:hover:text-white text-sm">✕ Cancel</button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">
        <div>
          <p className="text-slate-800 dark:text-gray-100 font-semibold text-sm">Ready to scan <span className="text-slate-600 dark:text-gray-300 font-mono">{org?.alias}</span></p>
          <p className="text-slate-500 text-xs mt-1">
            This will run <strong className="text-slate-700 dark:text-gray-200">{total} checks</strong> across {CHECK_CATEGORIES.length} categories.
            Each check makes one API call to your org — no data is modified.
          </p>
        </div>

        {CHECK_CATEGORIES.map(cat => {
          const catChecks = HEALTH_CHECKS.filter(c => c.category === cat);
          return (
            <div key={cat}>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                {CATEGORY_ICONS[cat] || "📋"} {cat}
              </p>
              <div className="flex flex-col gap-1">
                {catChecks.map(chk => (
                  <div key={chk.id} className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-gray-800 rounded-lg border border-slate-200 dark:border-gray-700">
                    <span className="text-slate-400 text-xs">◦</span>
                    <span className="text-slate-700 dark:text-gray-200 text-xs">{chk.label}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className="shrink-0 px-6 py-4 border-t border-slate-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex gap-3">
        <button onClick={onClose}
          className="flex-1 px-4 py-2.5 rounded-xl border border-slate-300 dark:border-gray-600 text-slate-600 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white hover:border-blue-400 text-sm transition-colors">
          Cancel
        </button>
        <button onClick={startChecks}
          className="flex-1 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors">
          ▶ Run {total} Checks
        </button>
      </div>
    </div>
  );

  // ── Running / results screen ───────────────────────────────────────────────

  async function loadDrill(chk) {
    if (!chk.drillQuery) return;
    setDrillRows(d => ({ ...d, [chk.id]: "loading" }));
    try {
      const res = await api("/api/soql", { method: "POST", body: JSON.stringify({ alias: org.alias, query: chk.drillQuery }) });
      setDrillRows(d => ({ ...d, [chk.id]: res.records || [] }));
    } catch (e) {
      setDrillRows(d => ({ ...d, [chk.id]: "error" }));
    }
  }

  function toggleExpand(chk) {
    const opening = !expanded[chk.id];
    setExpanded(e => ({ ...e, [chk.id]: opening }));
    if (opening && chk.drillQuery && !drillRows[chk.id]) loadDrill(chk);
  }

  return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-gray-900">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-800 border-b border-slate-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-slate-900 dark:text-gray-100">🏥 Org Health Check</span>
          {org && <span className="text-xs text-slate-500 font-mono">{org.alias}</span>}
        </div>
        <div className="flex items-center gap-3">
          {done && (
            <span className="text-xs">
              {fails > 0  && <span className="text-red-500 font-semibold mr-2">❌ {fails} failed</span>}
              {warns > 0  && <span className="text-yellow-600 dark:text-yellow-400 font-semibold mr-2">⚠️ {warns} warnings</span>}
              {fails === 0 && warns === 0 && <span className="text-green-600 dark:text-green-400 font-semibold">✅ All clear</span>}
            </span>
          )}
          <button onClick={onClose} className="text-slate-500 hover:text-slate-800 dark:hover:text-white text-sm">✕ Close</button>
        </div>
      </div>

      {/* Progress bar */}
      {!done && (
        <div className="shrink-0 px-4 py-2 bg-white dark:bg-gray-800 border-b border-slate-200 dark:border-gray-700">
          <div className="flex items-center justify-between text-xs text-slate-600 dark:text-gray-300 mb-1">
            <span>{current ? `Check ${checked + 1} of ${total} — ${current.label}` : "Starting…"}</span>
            <span>{checked} / {total}</span>
          </div>
          <div className="h-1.5 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full transition-all duration-300"
              style={{ width: `${(checked / total) * 100}%` }} />
          </div>
        </div>
      )}

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-4">
        {CHECK_CATEGORIES.map(cat => {
          const catChecks = HEALTH_CHECKS.filter(c => c.category === cat);
          const anyRun = catChecks.some(c => results[c.id] !== undefined);
          if (!anyRun) return null;
          return (
            <div key={cat}>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                {CATEGORY_ICONS[cat]} {cat}
              </p>
              <div className="flex flex-col gap-1.5">
                {catChecks.map(chk => {
                  const r = results[chk.id];
                  if (r === undefined) return null;
                  const isRunning = r === null;
                  const status    = isRunning ? "running" : r.status;
                  const canExpand = !isRunning && (status === "warn" || status === "fail");
                  const isOpen    = expanded[chk.id];
                  const drill     = drillRows[chk.id];

                  return (
                    <div key={chk.id}
                      className={`rounded-lg border overflow-hidden ${
                        status === "fail" ? "border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20"
                        : status === "warn" ? "border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20"
                        : "border-slate-200 dark:border-gray-700 bg-white dark:bg-gray-800"
                      }`}>
                      {/* Row */}
                      <div className="flex items-center gap-2 px-3 py-2">
                        <span className="text-sm shrink-0">
                          {isRunning ? <span className="animate-pulse">⏳</span> : STATUS_ICON[status]}
                        </span>
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-medium text-slate-800 dark:text-gray-100">{chk.label}</span>
                          {!isRunning && r.detail && (
                            <p className={`text-xs mt-0.5 ${STATUS_COLOR[status]}`}>{r.detail}</p>
                          )}
                          {isRunning && <p className="text-xs text-slate-400 mt-0.5 animate-pulse">Running…</p>}
                        </div>
                        {canExpand && (
                          <button onClick={() => toggleExpand(chk)}
                            className={`shrink-0 text-xs px-2 py-1 rounded-md border transition-colors font-medium ${
                              status === "fail"
                                ? "border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
                                : "border-yellow-300 dark:border-yellow-700 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-50 dark:hover:bg-yellow-900/30"
                            }`}>
                            {isOpen ? "▲ Hide" : "▼ Details"}
                          </button>
                        )}
                      </div>

                      {/* Expanded panel */}
                      {canExpand && isOpen && (
                        <div className={`border-t px-3 py-3 flex flex-col gap-3 ${
                          status === "fail" ? "border-red-200 dark:border-red-800" : "border-yellow-200 dark:border-yellow-800"
                        }`}>
                          {/* Fix tip */}
                          {chk.tip && (
                            <div className="flex gap-2">
                              <span className="text-base shrink-0">💡</span>
                              <div>
                                <p className="text-xs font-semibold text-slate-700 dark:text-gray-200 mb-1">How to fix</p>
                                <p className="text-xs text-slate-600 dark:text-gray-300 leading-relaxed">{chk.tip}</p>
                              </div>
                            </div>
                          )}

                          {/* Drill-down data */}
                          {chk.drillQuery && (
                            <div>
                              <p className="text-xs font-semibold text-slate-700 dark:text-gray-200 mb-1.5">📋 View Records</p>
                              {drill === "loading" && (
                                <p className="text-xs text-slate-400 animate-pulse">Loading records…</p>
                              )}
                              {drill === "error" && (
                                <p className="text-xs text-red-500">Could not load records</p>
                              )}
                              {Array.isArray(drill) && drill.length === 0 && (
                                <p className="text-xs text-slate-400">No records returned</p>
                              )}
                              {Array.isArray(drill) && drill.length > 0 && (() => {
                                const cols = Object.keys(drill[0]);
                                return (
                                  <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-gray-700">
                                    <table className="w-full text-xs">
                                      <thead>
                                        <tr className="bg-slate-100 dark:bg-gray-700">
                                          {cols.map(c => (
                                            <th key={c} className="px-2 py-1.5 text-left text-slate-700 dark:text-gray-200 font-semibold whitespace-nowrap">{c}</th>
                                          ))}
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {drill.map((row, ri) => (
                                          <tr key={ri} className="border-t border-slate-100 dark:border-gray-700 hover:bg-slate-50 dark:hover:bg-gray-700/50">
                                            {cols.map(c => (
                                              <td key={c} className="px-2 py-1.5 text-slate-700 dark:text-gray-200 font-mono whitespace-nowrap">
                                                {row[c] == null ? <span className="text-slate-400 italic">null</span> : String(row[c])}
                                              </td>
                                            ))}
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                );
                              })()}
                              <p className="text-xs text-slate-400 mt-1 font-mono">{chk.drillQuery}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
        {done && (
          <div className={`mt-2 px-4 py-3 rounded-xl border text-sm font-medium text-center ${
            fails > 0  ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300"
            : warns > 0 ? "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800 text-yellow-700 dark:text-yellow-300"
            : "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-300"
          }`}>
            {fails > 0  ? `${fails} check(s) failed — expand ❌ items above for details and fix tips`
            : warns > 0 ? `${warns} warning(s) found — expand ⚠️ items above for details and fix tips`
            : "✅ All checks passed — org looks healthy!"}
          </div>
        )}
      </div>
    </div>
  );
}

// Quick-action chip definitions — shown as cards + chips
const QUICK_ACTIONS = [
  {
    id: "record_counts",
    emoji: "📊",
    label: "Record Counts",
    description: "Top objects by volume",
    what: "Run COUNT() queries on Account, Contact, Lead, Opportunity, Case, Task, Event, and any available custom objects to show record volumes across your org.",
    apiCalls: "Up to 8 SOQL COUNT() queries",
    prompt: "List the top objects in this org by record count. Run SOQL COUNT() queries for Account, Contact, Lead, Opportunity, Case, Task, and Event. Show the results in a clear table.",
  },
  {
    id: "suggest_queries",
    emoji: "🔍",
    label: "Suggest Queries",
    description: "Diagnostic SOQL ideas",
    what: "Analyze the objects available in your org and suggest 5 useful diagnostic SOQL queries tailored to your specific data model.",
    apiCalls: "No API calls — uses org object list already loaded",
    prompt: "Based on the objects in this org, suggest 5 useful diagnostic SOQL queries with explanations of what each one reveals.",
  },
  {
    id: "data_model",
    emoji: "🗺",
    label: "Data Model",
    description: "Object relationships",
    what: "Explain the core Salesforce object relationships (Account → Contact → Opportunity → Case) and suggest practical SOQL joins you can run right now.",
    apiCalls: "No API calls — knowledge-based explanation",
    prompt: "Explain the relationship model between Account, Contact, Opportunity, and Case in Salesforce. Then provide 3-4 example SOQL queries using relationship traversal that I can run in the SOQL Runner.",
  },
];

export default function ClaudeChat({ org, ctx, setCtx, loadObjects }) {
  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState("");
  const [streaming,   setStreaming]   = useState(false);
  const [truncated,   setTruncated]   = useState(false);   // last reply hit the token limit
  const conn = useConnectionChoice("chat");                  // which saved AI connection this tab uses
  const [showHealth,  setShowHealth]  = useState(false);
  const [pendingAction, setPendingAction] = useState(null); // QUICK_ACTIONS entry
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // The object list loads in the background when this tab opens (once per org; App caches it and
  // skips a second call). Chat never waits for it: the prompt says whether it is there yet.
  useEffect(() => {
    if (org && !ctx.objectsLoaded && !ctx.objectsLoading) loadObjects?.();
  }, [org?.alias]);   // eslint-disable-line react-hooks/exhaustive-deps

  function buildSystem() {
    return buildChatSystem(org, ctx);
  }

  async function sendChip(prompt) {
    if (streaming) return;
    setInput("");
    await sendMessage(prompt);
  }

  async function sendMessage(overrideText) {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;
    if (!overrideText) setInput("");

    const userMsg = { role: "user", content: text };
    const newMsgs = [...messages, userMsg];
    setMessages(newMsgs);
    setStreaming(true);
    setTruncated(false);

    // Placeholder for assistant reply
    const placeholder = { role: "assistant", content: "" };
    setMessages((m) => [...m, placeholder]);

    let full = "";
    let skills = null;
    await apiStream(
      "/api/ai/chat",
      { messages: newMsgs, system: buildSystem(), connection: conn.selected || undefined },
      (delta) => {
        full += delta;
        setMessages((m) => {
          const updated = [...m];
          updated[updated.length - 1] = { role: "assistant", content: full, skills };
          return updated;
        });
      },
      () => {
        setStreaming(false);
        // Check for [SELECT_OBJECT: ...] action tag
        const match = full.match(/\[SELECT_OBJECT:\s*([^\]]+)\]/);
        if (match) handleSelectObject(match[1].trim(), newMsgs, full);
      },
      (err) => {
        setStreaming(false);
        setMessages((m) => {
          const updated = [...m];
          updated[updated.length - 1] = { role: "assistant", content: `❌ ${err}` };
          return updated;
        });
      },
      () => setTruncated(true),  // the model hit its token limit mid-answer
      (names) => { skills = names; }   // skills the backend really injected (shown once text arrives)
    );
  }

  async function handleSelectObject(apiName, prevMsgs, prevReply) {
    if (!org) return;
    // Already have fields?
    if (ctx.fields?.[apiName]) return;

    setMessages((m) => [...m, {
      role: "assistant",
      content: `📦 Loading fields for **${apiName}**…`,
      system: true,
    }]);

    try {
      const d = await api(`/api/orgs/${org.alias}/objects/${apiName}/fields`);
      const fields = d.fields || [];
      setCtx((c) => ({ ...c, fields: { ...c.fields, [apiName]: fields } }));

      const fieldLines = fields.map((f) => `  ${f.apiName} (${f.type})`).join("\n");
      const autoMsg = {
        role: "user",
        content: `[System: Fields loaded for ${apiName}. Here are all ${fields.length} fields:\n\n${fieldLines}\n\nPlease now write the SOQL query using exact API field names above.]`,
      };
      const nextMsgs = [...prevMsgs, { role: "assistant", content: prevReply }, autoMsg];
      setMessages((m) => [...m, autoMsg]);

      setStreaming(true);
      const autoPlaceholder = { role: "assistant", content: "" };
      setMessages((m) => [...m, autoPlaceholder]);

      let autoFull = "";
      let autoSkills = null;
      await apiStream(
        "/api/ai/chat",
        { messages: nextMsgs, system: buildSystem(), connection: conn.selected || undefined },
        (delta) => {
          autoFull += delta;
          setMessages((m) => {
            const updated = [...m];
            updated[updated.length - 1] = { role: "assistant", content: autoFull, skills: autoSkills };
            return updated;
          });
        },
        () => setStreaming(false),
        (err) => {
          setStreaming(false);
          setMessages((m) => {
            const updated = [...m];
            updated[updated.length - 1] = { role: "assistant", content: `❌ ${err}` };
            return updated;
          });
        },
        () => setTruncated(true),
        (names) => { autoSkills = names; }
      );
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `❌ Failed to load fields: ${e.message}`, system: true }]);
    }
  }

  if (showHealth) return <OrgHealthCheck org={org} onClose={() => setShowHealth(false)} />;

  // ── Confirm modal for quick-action cards ────────────────────────────────────
  if (pendingAction) return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-gray-900">
      <div className="shrink-0 flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-800 border-b border-slate-200 dark:border-gray-700">
        <span className="text-base font-bold text-slate-900 dark:text-gray-100">{pendingAction.emoji} {pendingAction.label}</span>
        <button onClick={() => setPendingAction(null)} className="text-slate-500 hover:text-slate-800 dark:hover:text-white text-sm">✕ Cancel</button>
      </div>
      <div className="flex-1 px-6 py-6 flex flex-col gap-5">
        <div>
          <p className="text-slate-800 dark:text-gray-100 font-semibold text-sm mb-1">Here's what I'll do</p>
          <p className="text-slate-600 dark:text-gray-300 text-sm leading-relaxed">{pendingAction.what}</p>
        </div>
        <div className="px-4 py-3 bg-slate-100 dark:bg-gray-700 rounded-xl border border-slate-200 dark:border-gray-700">
          <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1">API Usage</p>
          <p className="text-slate-700 dark:text-gray-200 text-xs">{pendingAction.apiCalls}</p>
        </div>
        <div className="px-4 py-3 bg-slate-100 dark:bg-gray-700 rounded-xl border border-slate-200 dark:border-gray-700">
          <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1">Prompt</p>
          <p className="text-slate-600 dark:text-gray-300 text-xs font-mono leading-relaxed">{pendingAction.prompt}</p>
        </div>
      </div>
      <div className="shrink-0 px-6 py-4 border-t border-slate-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex gap-3">
        <button onClick={() => setPendingAction(null)}
          className="flex-1 px-4 py-2.5 rounded-xl border border-slate-300 dark:border-gray-600 text-slate-600 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white hover:border-blue-400 text-sm transition-colors">
          Cancel
        </button>
        <button onClick={() => { const p = pendingAction.prompt; setPendingAction(null); sendChip(p); }}
          className="flex-1 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors">
          ▶ Proceed
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-gray-900">
      {/* Quick chips */}
      <div className="shrink-0 flex flex-wrap gap-2 px-4 py-2.5 border-b border-slate-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <button disabled={!org} onClick={() => setShowHealth(true)}
          className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-full border border-blue-400 transition-colors font-medium">
          🏥 Org Health Check
        </button>
        {QUICK_ACTIONS.map(a => (
          <button key={a.id} disabled={streaming || !org}
            onClick={() => setPendingAction(a)}
            className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-full border border-blue-400 transition-colors font-medium">
            {a.emoji} {a.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <ConnectionPicker {...conn} onChange={conn.choose} disabled={streaming} dark={false} />
          {messages.length > 0 && (
            <button onClick={() => { setMessages([]); setTruncated(false); }} disabled={streaming}
              className="px-3 py-1 text-xs text-slate-400 hover:text-red-500 transition-colors">
              🗑 Clear
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center mt-12 text-sm px-6">
            <img src="/icon-128.png" alt="Avio" className="w-12 h-12 object-contain mx-auto mb-4" />
            <p className="font-semibold text-slate-900 dark:text-gray-100 text-base">Ask me anything about your Salesforce org.</p>
            <p className="text-slate-400 text-xs mt-2">
              {!org
                ? "Select an org to ask about its objects. You can ask general Salesforce questions now."
                : ctx.objectsLoading
                ? "Loading your org's objects in the background. You can start chatting now."
                : ctx.objects?.length
                ? `I know your org's ${ctx.objects.length} objects, and the fields you open.`
                : "Ask me anything about Salesforce."}
            </p>
            <div className="mt-6 grid grid-cols-2 gap-2 max-w-sm mx-auto">
              <button onClick={() => setShowHealth(true)} disabled={!org}
                className="p-3 bg-white dark:bg-gray-800 hover:bg-slate-50 dark:hover:bg-gray-700/50 border border-slate-200 dark:border-gray-700 rounded-xl text-left transition-colors disabled:opacity-40">
                <p className="text-sm">🏥</p>
                <p className="text-slate-800 dark:text-gray-100 text-xs font-medium mt-1">Org Health Check</p>
                <p className="text-slate-400 text-xs mt-0.5">16 checks · security, limits & metadata</p>
              </button>
              {QUICK_ACTIONS.map(a => (
                <button key={a.id} disabled={streaming || !org}
                  onClick={() => setPendingAction(a)}
                  className="p-3 bg-white dark:bg-gray-800 hover:bg-slate-50 dark:hover:bg-gray-700/50 border border-slate-200 dark:border-gray-700 rounded-xl text-left transition-colors disabled:opacity-40">
                  <p className="text-sm">{a.emoji}</p>
                  <p className="text-slate-800 dark:text-gray-100 text-xs font-medium mt-1">{a.label}</p>
                  <p className="text-slate-400 text-xs mt-0.5">{a.description}</p>
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-2xl rounded-2xl px-4 py-2.5 text-sm ${
              msg.role === "user"
                ? "bg-blue-600 text-white rounded-br-sm"
                : msg.system
                ? "bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-300 border border-yellow-200 dark:border-yellow-800 rounded-bl-sm text-xs font-mono"
                : "bg-white dark:bg-gray-800 text-slate-800 dark:text-gray-100 border border-slate-200 dark:border-gray-700 rounded-bl-sm"
            }`}>
              <MarkdownText text={msg.content} />
              {msg.role === "assistant" && !msg.system && msg.content && <SkillsUsed skills={msg.skills} />}
            </div>
          </div>
        ))}
        {streaming && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-2xl rounded-bl-sm px-4 py-2.5">
              <Spinner label="Thinking…" />
              {!messages[messages.length - 1]?.content && <SlowHint />}
            </div>
          </div>
        )}
        {truncated && !streaming && (
          <div className="max-w-2xl">
            <TruncatedNotice onContinue={() => sendMessage(CONTINUE_PROMPT)} />
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-slate-200 dark:border-gray-700 p-3 flex gap-2 bg-white dark:bg-gray-800">
        <textarea
          className="flex-1 text-sm border border-slate-300 dark:border-gray-600 rounded-xl px-3 py-2 bg-slate-50 dark:bg-gray-900 text-slate-800 dark:text-gray-100 placeholder-slate-400 resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
          rows={2}
          placeholder="Ask about your org, request a SOQL query…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
          }}
          disabled={streaming}
        />
        <button
          onClick={() => sendMessage()}
          disabled={streaming || !input.trim()}
          className="px-4 py-2 bg-blue-500 hover:bg-blue-400 disabled:opacity-40 text-white rounded-xl text-sm font-medium self-end transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  );
}

// Minimal markdown renderer for bold/code/newlines
function MarkdownText({ text }) {
  if (!text) return null;
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**"))
          return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (p.startsWith("`") && p.endsWith("`"))
          return <code key={i} className="font-mono text-xs bg-slate-100 dark:bg-gray-700 text-slate-800 dark:text-gray-100 px-1 rounded">{p.slice(1, -1)}</code>;
        return <span key={i}>{p.split("\n").map((ln, j) => <span key={j}>{ln}{j < p.split("\n").length - 1 && <br />}</span>)}</span>;
      })}
    </>
  );
}
