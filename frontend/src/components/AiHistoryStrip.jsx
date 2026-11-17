import { useEffect, useRef, useState } from "react";
import { api, isTauri, openSaveDialog } from "../api/client";
import { debugLog } from "../debugLog";
import { useSessionState } from "../sessionStore";
import {
  RETENTION_DAYS, SURFACES, cleanMessages, defaultFileName, estimateTokens, getMessages, loadIntoSurface,
  checkFileName, markSaved, parseChatFile, restoreDismissedKey, serializeChat, toMarkdown,
} from "../chatHistory";

const THEMES = {
  dark: {
    row:   "bg-slate-800/60 border-b border-slate-700 text-slate-300",
    btn:   "bg-slate-700 hover:bg-slate-600 text-white",
    quiet: "text-slate-400 hover:text-white",
    warn:  "text-amber-300",
    err:   "text-red-300",
    ok:    "text-emerald-300",
  },
  auto: {
    row:   "bg-white dark:bg-gray-800 border-b border-slate-200 dark:border-gray-700 text-slate-600 dark:text-gray-300",
    btn:   "bg-slate-100 hover:bg-slate-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-slate-800 dark:text-white",
    quiet: "text-slate-500 hover:text-slate-900 dark:text-gray-400 dark:hover:text-white",
    warn:  "text-amber-600 dark:text-amber-300",
    err:   "text-red-600 dark:text-red-300",
    ok:    "text-emerald-600 dark:text-emerald-300",
  },
};

const when = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

async function appVersion() {
  if (!isTauri()) return "";
  try { return await (await import("@tauri-apps/api/app")).getVersion(); } catch { return ""; }
}

// Save or Load for one AI conversation, plus the "restore your last conversation" offer.
//   surface: "apex" | "soql" | "chat"     busy: a reply is streaming (loading is blocked)
export default function AiHistoryStrip({ surface, busy = false, variant = "dark" }) {
  const t = THEMES[variant] || THEMES.dark;
  const [saved, setSaved]         = useState(null);                                   // newest saved copy for this surface
  const [dismissed, setDismissed] = useSessionState(restoreDismissedKey(surface), false);
  const [note, setNote]           = useState(null);                                   // { kind: "ok"|"err", text }
  const [pending, setPending]     = useState(null);                                   // a loaded file waiting for Replace / Append
  const fileRef = useRef(null);
  const noteTimer = useRef(null);
  const [messages] = useSessionState(SURFACES[surface].key, []);
  const hasMessages = cleanMessages(messages).length > 0;

  function say(kind, text, ms = 12000) {
    clearTimeout(noteTimer.current);
    setNote({ kind, text });
    if (ms) noteTimer.current = setTimeout(() => setNote(null), ms);
  }
  useEffect(() => () => clearTimeout(noteTimer.current), []);

  async function refreshSaved() {
    try {
      const d = await api(`/api/chats?surface=${surface}`);
      setSaved(d.chats?.[0] || null);
    } catch { setSaved(null); }   // backend not ready or older: just no offer
  }
  // The panel stays mounted when a conversation is emptied (Clear, or a Switch Org that saved it),
  // so look again each time it becomes empty, not only on mount.
  useEffect(() => { if (!hasMessages) refreshSaved(); }, [surface, hasMessages]);   // eslint-disable-line react-hooks/exhaustive-deps

  function applyLoaded(chatMessages, mode, label) {
    loadIntoSurface(surface, chatMessages, mode);
    const total = getMessages(surface).length;
    say("ok", `${label}: ${plural(chatMessages.length, "message")} loaded` +
      (mode === "append" ? ` (${total} in this conversation)` : "") +
      `. About ${estimateTokens(getMessages(surface)).toLocaleString()} tokens will be sent to the model with your next message.`);
  }

  // ── Restore the copy saved when Avio was last closed ──
  async function restore() {
    try {
      const chat = await api(`/api/chats/${saved.id}`);
      applyLoaded(chat.messages, "replace", "Restored");
      setDismissed(true);
    } catch (e) {
      say("err", `Could not restore: ${String(e?.message || e).split("\n")[0]}`);
      refreshSaved();
    }
  }
  async function discardSaved() {
    try { await api("/api/chats/delete", { method: "POST", body: JSON.stringify({ id: saved.id }) }); } catch { /* already gone */ }
    setSaved(null);
  }

  // ── Save to a file the user chooses (never expires) ──
  async function saveToFile() {
    const clean = cleanMessages(messages);
    if (!clean.length) return;
    const chat = serializeChat(surface, clean, { appVersion: await appVersion() });
    const fileName = defaultFileName(surface, "json");
    try {
      if (!isTauri()) {                                       // browser dev mode
        const blob = new Blob([JSON.stringify(chat, null, 2)], { type: "application/json" });
        const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: fileName });
        a.click();
        URL.revokeObjectURL(a.href);
        markSaved(surface);
        return;
      }
      const path = await openSaveDialog({
        title: "Save conversation",
        defaultPath: fileName,
        filters: [
          { name: "Avio conversation (.json: can be loaded again)", extensions: ["json"] },
          { name: "Readable text (.md: for reading only, cannot be loaded)", extensions: ["md"] },
        ],
      });
      if (!path) return;                                       // cancelled
      const isMd = /\.md$/i.test(path);
      const finalPath = isMd || /\.json$/i.test(path) ? path : `${path}.json`;
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("write_file", {
        path: finalPath,
        content: isMd ? toMarkdown(chat) : JSON.stringify(chat, null, 2) + "\n",
      });
      markSaved(surface);
      say("ok", `Saved ${plural(chat.messages.length, "message")} to ${finalPath}` +
        (isMd ? ". This readable copy cannot be loaded back: save as .json to continue it later." : ""));
    } catch (e) {
      debugLog(`Save conversation failed: ${e?.message || e}`, "error");
      say("err", `Could not save the conversation: ${e?.message || e}`);
    }
  }

  // ── Load a .json file ──
  async function onFilePicked(e) {
    const file = e.target.files?.[0];
    e.target.value = "";                                       // allow picking the same file again
    if (!file) return;
    const wrongType = checkFileName(file.name);
    if (wrongType) { say("err", wrongType); return; }
    let text;
    try { text = await file.text(); } catch { say("err", "That file could not be read."); return; }
    const r = parseChatFile(text);
    if (!r.ok) { say("err", r.error); return; }
    if (hasMessages) { setPending({ chat: r.chat, name: file.name }); setNote(null); return; }
    applyLoaded(r.chat.messages, "replace", file.name);
    if (r.chat.ignored) say("ok", `${file.name}: ${plural(r.chat.messages.length, "message")} loaded; ${r.chat.ignored} unusable entries were ignored.`);
  }
  function choose(mode) {
    const p = pending;
    setPending(null);
    if (p) applyLoaded(p.chat.messages, mode, p.name);
  }

  const offer = saved && !dismissed && !hasMessages && !pending;
  const small = "px-2 py-0.5 rounded text-[11px] font-medium transition-colors disabled:opacity-40";

  return (
    <div className={`shrink-0 flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1.5 text-xs ${t.row}`}>
      <div className="flex-1 min-w-0 flex flex-wrap items-center gap-x-2 gap-y-1">
        {offer && (
          <>
            <span>
              Restore your last {SURFACES[surface].label} conversation (saved {when(saved.saved_at)},{" "}
              {plural(saved.count, "message")}; kept until {when(saved.expires_at)})?
            </span>
            <button disabled={busy} onClick={restore} className={`${small} ${t.btn}`}>Restore</button>
            <button onClick={() => setDismissed(true)} className={`${small} ${t.quiet}`}>Dismiss</button>
            <button onClick={discardSaved} className={`${small} ${t.quiet}`} title="Delete the saved copy now">Delete</button>
          </>
        )}
        {pending && (
          <>
            <span className={t.warn}>
              This conversation already has messages. Load {plural(pending.chat.messages.length, "message")} from {pending.name}:
            </span>
            <button onClick={() => choose("replace")} className={`${small} ${t.btn}`}>Replace</button>
            <button onClick={() => choose("append")} className={`${small} ${t.btn}`}>Append</button>
            <button onClick={() => setPending(null)} className={`${small} ${t.quiet}`}>Cancel</button>
          </>
        )}
        {note && !pending && (
          <span className={`min-w-0 break-words ${note.kind === "err" ? t.err : t.ok}`} role={note.kind === "err" ? "alert" : "status"}>
            {note.text}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          onClick={saveToFile}
          disabled={!hasMessages}
          className={`${small} ${t.btn}`}
          title={`Save this conversation to a file: .json to load again later, .md only to read. Avio also offers to keep it for ${RETENTION_DAYS} days when you close the app.`}
        >
          💾 Save
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className={`${small} ${t.btn}`}
          title="Load a conversation saved from Avio (.json). It becomes context for the model, so it uses tokens."
        >
          📂 Load
        </button>
        <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={onFilePicked} />
      </div>
    </div>
  );
}
