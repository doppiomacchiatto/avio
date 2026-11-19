import { useCallback, useEffect, useState } from "react";
import { api, isLocalUrl } from "./api/client";

// Saved AI connections (provider + URL + model; the API key stays in the OS keystore and is
// never sent to the UI). Shared by Settings and every AI panel, so one cached copy lives here.
let cache = null;          // { connections, default, storage, presets }
let inflight = null;
const listeners = new Set();

export function loadConnections() {
  inflight = api("/api/ai/connections")
    .then((d) => { cache = d; listeners.forEach((fn) => fn(d)); return d; })
    .catch(() => cache)
    .finally(() => { inflight = null; });
  return inflight;
}

// Call after Settings adds, edits or deletes a connection so open panels refresh.
export function notifyConnectionsChanged() {
  return loadConnections();
}

export function useConnections() {
  const [data, setData] = useState(cache);
  useEffect(() => {
    listeners.add(setData);
    if (cache) setData(cache);
    if (!cache && !inflight) loadConnections();
    return () => { listeners.delete(setData); };
  }, []);
  return data || { connections: [], default: "" };
}

// Which connection one panel ("apex", "soql", "chat") uses. "" means the default connection.
// The choice is remembered per panel and falls back to the default if that connection is deleted.
const storageKey = (panel) => `avio.connection.${panel}`;

export function useConnectionChoice(panel) {
  const data = useConnections();
  const [chosen, setChosen] = useState(() => {
    try { return localStorage.getItem(storageKey(panel)) || ""; } catch { return ""; }
  });
  const selected = chosen && data.connections.some((c) => c.id === chosen) ? chosen : "";
  const choose = useCallback((id) => {
    setChosen(id);
    try { id ? localStorage.setItem(storageKey(panel), id) : localStorage.removeItem(storageKey(panel)); } catch { /* storage unavailable */ }
  }, [panel]);
  const active = data.connections.find((c) => c.id === (selected || data.default));
  return { connections: data.connections, defaultId: data.default, selected, choose, isLocal: isLocalUrl(active?.base_url) };
}
