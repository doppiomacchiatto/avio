// In-memory state that outlives a component. App mounts only the active tab, so anything held in
// a tab's own useState (an AI conversation, whether its panel is open) is lost when you switch
// tabs and come back. State kept here lives until the app is closed. Nothing is written to disk.
//
// The setters work against this store, not against a mounted component, so a reply that finishes
// streaming while you are on another tab still lands in the history.
import { useCallback, useSyncExternalStore } from "react";

const values = new Map();
const listeners = new Set();
const notify = () => listeners.forEach((f) => f());

export function getSession(key, initial) {
  if (!values.has(key)) values.set(key, typeof initial === "function" ? initial() : initial);
  return values.get(key);
}

// `next` may be a value or an updater function (prev) => value, like React's setState.
export function setSession(key, next) {
  const prev = values.get(key);
  const value = typeof next === "function" ? next(prev) : next;
  if (!Object.is(value, prev)) {
    values.set(key, value);
    notify();
  }
  return value;
}

// Forget every key that starts with `prefix` (all of them by default).
export function clearSession(prefix = "") {
  for (const key of [...values.keys()]) if (key.startsWith(prefix)) values.delete(key);
  notify();
}

const subscribe = (f) => {
  listeners.add(f);
  return () => listeners.delete(f);
};
export const subscribeSession = subscribe;   // for tests

export function useSessionState(key, initial) {
  const snapshot = () => getSession(key, initial);
  const value = useSyncExternalStore(subscribe, snapshot, snapshot);
  const set = useCallback((next) => setSession(key, next), [key]);
  return [value, set];
}
