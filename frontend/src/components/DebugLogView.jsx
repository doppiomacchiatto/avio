import { useLayoutEffect, useRef, useState } from "react";
import { useDebugLog, useDebugScope, setDebugScope, clearDebugLog } from "../debugLog";

const LEVEL_STYLE = {
  info:  "text-green-300",
  start: "text-blue-300",
  done:  "text-green-400",
  warn:  "text-yellow-300",
  error: "text-red-400",
};

const LEVEL_ICON = { info: "ℹ️", start: "▶", done: "✅", warn: "⚠️", error: "❌" };

const BTN =
  "text-xs font-normal px-2 py-0.5 rounded border border-gray-300 dark:border-gray-500 text-gray-600 dark:text-gray-300 " +
  "hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-40";

function fmt(ts) {
  const d = new Date(ts);
  return d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

/**
 * The debug log: a header with filter / copy / clear and, while `open`, the entries.
 * tab:      the active tab id. When set, the header offers "This tab" / "All".
 * onToggle: makes the title a collapse / expand button (the dock).
 * onClose:  adds a ✕ button (the startup overlay).
 */
export default function DebugLogView({ tab = null, open = true, onToggle, onClose }) {
  const entries = useDebugLog();
  const scope = useDebugScope();   // in the store, so the 🐞 button counts the same entries
  const [filter, setFilter] = useState("");
  const [copied, setCopied] = useState(false);
  const bodyRef = useRef(null);
  const stickRef = useRef(true);

  const byTab = tab != null && scope === "tab";
  const q = filter.trim().toLowerCase();
  const inScope = byTab ? entries.filter((e) => e.source === tab) : entries;
  const shown = q ? inScope.filter((e) => e.msg.toLowerCase().includes(q)) : inScope;
  const lastId = shown.length ? shown[shown.length - 1].id : 0;

  // Follow new entries while the view is scrolled to the bottom; leave it alone once the user scrolls up.
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (open && el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [lastId, open]);

  function onScroll() {
    const el = bodyRef.current;
    if (el) stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  }

  function copyAll() {
    const text = shown.map((e) => `${fmt(e.ts)} [${e.level}]${e.source ? ` [${e.source}]` : ""} ${e.msg}`).join("\n");
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  }

  const title = `🐞 Debug Log${inScope.length > 0 ? ` (${inScope.length})` : ""}`;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="h-7 shrink-0 flex items-center gap-2 px-4 bg-gray-100 dark:bg-gray-700 text-xs font-mono font-semibold text-gray-600 dark:text-gray-300">
        {onToggle ? (
          <button
            onClick={onToggle}
            aria-expanded={open}
            className="flex-1 flex items-center justify-between text-left py-0.5 hover:text-gray-900 dark:hover:text-white"
          >
            <span>{title}</span>
            <span className="text-gray-400 ml-2">{open ? "▼ collapse" : "▲ expand"}</span>
          </button>
        ) : (
          <span className="flex-1">{title}</span>
        )}
        {open ? (
          <>
            {tab != null ? (
              <div className="flex rounded border border-gray-300 dark:border-gray-500 overflow-hidden" role="group" aria-label="Which entries to show">
                {[["tab", "This tab"], ["all", "All"]].map(([id, label]) => (
                  <button
                    key={id}
                    onClick={() => setDebugScope(id)}
                    aria-pressed={scope === id}
                    className={`text-xs font-normal px-2 py-0.5 transition-colors ${
                      scope === id
                        ? "bg-blue-600 text-white"
                        : "text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            ) : null}
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter…"
              aria-label="Filter log entries"
              className="text-xs font-normal w-36 px-2 py-0.5 rounded border border-gray-300 dark:border-gray-500 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 outline-none focus:border-blue-400"
            />
            <button onClick={copyAll} disabled={shown.length === 0} className={BTN}>{copied ? "Copied" : "Copy"}</button>
            <button
              onClick={() => clearDebugLog(byTab ? tab : undefined)}
              disabled={inScope.length === 0}
              title={byTab ? "Clear this tab's entries" : "Clear all entries"}
              className={BTN}
            >
              Clear
            </button>
          </>
        ) : null}
        {onClose ? (
          <button onClick={onClose} className="text-gray-400 hover:text-gray-900 dark:hover:text-white text-base leading-none" title="Close">✕</button>
        ) : null}
      </div>

      {open ? (
        <div ref={bodyRef} onScroll={onScroll} className="flex-1 min-h-0 overflow-y-auto bg-gray-900 px-3 py-2 font-mono text-xs">
          {inScope.length === 0 ? (
            <span className="text-gray-500">No log entries yet.</span>
          ) : shown.length === 0 ? (
            <span className="text-gray-500">No entries match “{filter}”.</span>
          ) : (
            shown.map((e) => (
              <div key={e.id} className="flex gap-2 leading-5">
                <span className="text-gray-500 shrink-0">{fmt(e.ts)}</span>
                {byTab || !e.source ? null : <span className="text-gray-500 shrink-0">[{e.source}]</span>}
                <span className="shrink-0">{LEVEL_ICON[e.level] || LEVEL_ICON.info}</span>
                <span className={`whitespace-pre-wrap break-all ${LEVEL_STYLE[e.level] || LEVEL_STYLE.info}`}>{e.msg}</span>
              </div>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
