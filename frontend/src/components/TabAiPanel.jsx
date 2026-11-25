// The AI panel for the FLS Explorer, Profiles & PermSets and REST Explorer tabs. It works like the SOQL Runner's
// panel (same streaming, Stop, Continue, connection picker, Save / Load strip); what differs per tab is passed in:
//   surface      "fls" | "profiles" | "rest" (chatHistory.SURFACES); its session keys are `${surface}.ai.*`
//   buildSystem  () => the system prompt, built from what the tab shows right now (see tabAi.js)
//   chips        [{ label, prompt }] quick prompts
//   action       optional { langs, label, onUse(content, lang) }: a button on code blocks in those languages
//   forceSkills  skills the backend always injects for this tab
import { useEffect, useRef } from "react";
import { apiStream, stopStream } from "../api/client";
import Spinner from "./Spinner";
import { parseBlocks, isLang, CONTINUE_PROMPT } from "../aiBlocks";
import { SlowHint, StopButton, StoppedNotice, TruncatedNotice, SkillsUsed } from "./AiNotices";
import ConnectionPicker from "./ConnectionPicker";
import { useConnectionChoice } from "../connections";
import { useSessionState } from "../sessionStore";
import AiHistoryStrip from "./AiHistoryStrip";

function AssistantMessage({ content, action }) {
  return (
    <div className="flex flex-col gap-2">
      {parseBlocks(content).map((b, i) => b.type === "text" ? (
        <p key={i} className="text-xs text-gray-200 whitespace-pre-wrap leading-relaxed">{b.content}</p>
      ) : (
        <div key={i} className="relative group">
          <pre className="text-xs font-mono bg-gray-950 border border-gray-700 rounded p-3 overflow-x-auto text-green-300 leading-5">{b.content}</pre>
          <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={() => navigator.clipboard?.writeText(b.content)}
              className="px-2 py-0.5 text-xs bg-slate-700 hover:bg-slate-600 text-white rounded font-medium">Copy</button>
            {action && isLang(b.lang, action.langs) && (
              <button onClick={() => action.onUse(b.content, b.lang)}
                className="px-2 py-0.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded font-medium">{action.label}</button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// The violet "✨ AI" button that opens and closes the panel (same look as the SOQL Runner's).
export function AiToggle({ open, onToggle, className = "" }) {
  return (
    <button
      onClick={onToggle}
      className={`shrink-0 px-3 py-1 rounded text-xs font-semibold border transition-colors ${
        open
          ? "bg-violet-700 hover:bg-violet-800 text-white border-violet-600"
          : "bg-gray-100 dark:bg-gray-700 hover:bg-violet-50 dark:hover:bg-violet-900/30 text-violet-700 dark:text-violet-300 border-violet-300 dark:border-violet-700"
      } ${className}`}
      title="Toggle AI assistant"
    >
      ✨ AI
    </button>
  );
}

export default function TabAiPanel({ surface, buildSystem, chips = [], action, forceSkills, placeholder, emptyHint, onClose }) {
  // The conversation lives in the session store, not in this component: switching tabs unmounts it.
  const [messages,     setMessages]     = useSessionState(`${surface}.ai.messages`, []);
  const [input,        setInput]        = useSessionState(`${surface}.ai.input`, "");
  const [streaming,    setStreaming]    = useSessionState(`${surface}.ai.streaming`, false);
  const [streamBuf,    setStreamBuf]    = useSessionState(`${surface}.ai.streamBuf`, "");
  const [truncated,    setTruncated]    = useSessionState(`${surface}.ai.truncated`, false);
  const [streamSkills, setStreamSkills] = useSessionState(`${surface}.ai.streamSkills`, null);
  const conn = useConnectionChoice(surface);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamBuf]);

  async function sendMessage(userText) {
    if (!userText.trim() || streaming) return;
    const newMessages = [...messages, { role: "user", content: userText.trim() }];
    setMessages(newMessages);
    setInput("");
    setStreaming(true);
    setStreamBuf("");
    setTruncated(false);
    setStreamSkills(null);
    let fullText = "";
    let skills = null;

    await apiStream(
      "/api/claude/chat",
      { messages: newMessages, system: buildSystem(), force_skills: forceSkills?.length ? forceSkills : undefined,
        connection: conn.selected || undefined },
      (delta) => { fullText += delta; setStreamBuf(fullText); },
      () => { setMessages(prev => [...prev, { role: "assistant", content: fullText, skills }]); setStreaming(false); setStreamBuf(""); setStreamSkills(null); },
      (err) => {
        setMessages(prev => [...prev, { role: "assistant", content: /No API key/i.test(err) ? `🔑 ${err}` : `⚠ Error: ${err}` }]);
        setStreaming(false); setStreamBuf("");
      },
      () => setTruncated(true),
      (names) => { skills = names; setStreamSkills(names); },
      { surface },
    );
  }

  // Stop: keep what has arrived (marked as stopped) and free the panel. The backend closes the provider connection.
  function stopReply() {
    if (!stopStream(surface)) return;
    if (streamBuf.trim()) {
      setMessages(prev => [...prev, { role: "assistant", content: streamBuf, skills: streamSkills, stopped: true }]);
    }
    setStreaming(false); setStreamBuf(""); setStreamSkills(null); setTruncated(false);
  }

  return (
    <div className="flex flex-col h-full bg-slate-900 border-l border-slate-700">
      <div className="shrink-0 flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700">
        <span className="text-sm font-semibold text-white">✨ AI</span>
        <div className="flex items-center gap-2">
          <ConnectionPicker {...conn} onChange={conn.choose} disabled={streaming} />
          {messages.length > 0 && (
            <button onClick={() => { setMessages([]); setStreamBuf(""); setTruncated(false); }} className="text-xs text-slate-300 hover:text-red-400">🗑 Clear</button>
          )}
          <button onClick={onClose} className="text-slate-300 hover:text-white text-sm" title="Close the AI panel">✕</button>
        </div>
      </div>

      <AiHistoryStrip surface={surface} busy={streaming} />

      {chips.length > 0 && (
        <div className="shrink-0 flex flex-wrap gap-1.5 px-3 py-2 border-b border-slate-700">
          {chips.map((c) => (
            <button key={c.label} disabled={streaming} onClick={() => sendMessage(c.prompt)}
              className="px-2.5 py-1 text-xs bg-slate-700 hover:bg-blue-700 disabled:opacity-40 text-white rounded-full border border-blue-600 transition-colors font-medium">
              {c.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-4 min-h-0">
        {messages.length === 0 && !streaming && (
          <div className="text-xs text-slate-300 text-center pt-6 leading-relaxed px-2">
            {emptyHint?.[0]}<br/>
            <span className="text-slate-400">{emptyHint?.[1]}</span>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex flex-col gap-1 ${msg.role === "user" ? "items-end" : "items-start"}`}>
            {msg.role === "user"
              ? <div className="max-w-[90%] bg-blue-600 text-white text-xs px-3 py-2 rounded-2xl rounded-tr-sm whitespace-pre-wrap">{msg.content}</div>
              : <div className="w-full"><AssistantMessage content={msg.content} action={action} /><SkillsUsed skills={msg.skills} dark />{msg.stopped && <StoppedNotice dark />}</div>
            }
          </div>
        ))}
        {streaming && streamBuf && <div className="w-full"><AssistantMessage content={streamBuf} action={action} /><SkillsUsed skills={streamSkills} dark /></div>}
        {streaming && !streamBuf && (
          <div className="text-xs text-slate-300">
            <div className="flex items-center gap-2"><Spinner label="" /><span>Thinking…</span></div>
            <SkillsUsed skills={streamSkills} dark />
            <SlowHint dark local={conn.isLocal} />
          </div>
        )}
        {truncated && !streaming && (
          <TruncatedNotice dark onContinue={() => sendMessage(CONTINUE_PROMPT)} />
        )}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 px-3 py-2 border-t border-slate-700">
        <div className="flex gap-2 items-end">
          <textarea
            className="flex-1 min-h-[36px] max-h-32 text-xs border border-slate-600 rounded-lg px-3 py-2 bg-slate-800 text-slate-50 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none leading-5"
            placeholder={placeholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
            rows={1}
          />
          {streaming
            ? <StopButton onStop={stopReply} className="px-3 py-2 rounded-lg text-xs" />
            : <button onClick={() => sendMessage(input)} disabled={!input.trim()}
                className="shrink-0 px-3 py-2 bg-blue-500 hover:bg-blue-400 disabled:opacity-40 text-white rounded-lg text-xs font-semibold">↑</button>}
        </div>
        <p className="text-xs text-slate-400 mt-1">↵ send · Shift+↵ newline</p>
      </div>
    </div>
  );
}
