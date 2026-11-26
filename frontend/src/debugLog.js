import { useSyncExternalStore } from "react";

// The app's one debug log. Every tab, the API client and the startup screens write here, and the debug
// dock at the bottom of the window (components/DebugDock.jsx) shows it. Each entry is tagged with the tab
// that was active when it was written, so the dock can show "This tab" or "All".

const MAX_ENTRIES = 500;

// Page code says "success"; the log calls that "done".
const LEVEL_ALIASES = { success: "done" };

let entries = [];
let nextId = 1;
let source = null;   // the active tab, set by App on every tab change
let open = false;    // whether the dock is expanded

const listeners = new Set();

function emit() {
  for (const l of listeners) l();
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Tag the entries written from now on with this tab id. */
export function setDebugSource(tab) {
  source = tab;
}

/**
 * Add an entry. level: info | start | done (or success) | warn | error.
 * An error opens the dock unless `reveal` is false (the API client's request lines: the page that made the
 * request logs its own error when the failure matters, and a background request should not pop the dock).
 */
export function debugLog(msg, level = "info", { reveal } = {}) {
  const lvl = LEVEL_ALIASES[level] || level;
  const entry = { id: nextId++, ts: Date.now(), level: lvl, msg: String(msg), source };
  entries = [...entries.slice(-(MAX_ENTRIES - 1)), entry];
  if (reveal ?? lvl === "error") open = true;
  emit();
  return entry;
}

/** Remove every entry, or only the entries written while `tab` was active. */
export function clearDebugLog(tab) {
  entries = tab == null ? [] : entries.filter((e) => e.source !== tab);
  emit();
}

export function setDebugOpen(value) {
  const next = typeof value === "function" ? value(open) : value;
  if (next === open) return;
  open = next;
  emit();
}

export function useDebugLog() {
  return useSyncExternalStore(subscribe, () => entries);
}

/** Only the count, so a badge does not re-render on anything else. */
export function useDebugLogCount() {
  return useSyncExternalStore(subscribe, () => entries.length);
}

export function useDebugOpen() {
  return useSyncExternalStore(subscribe, () => open);
}
