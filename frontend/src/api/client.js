/**
 * API client — when running inside Tauri, proxies all requests through Rust
 * (invoke api_get / api_post) to avoid WebView CSP restrictions.
 * Falls back to plain fetch for browser-only dev.
 */

import { debugLog } from "../debugLog";

let _invoke = null;

async function getInvoke() {
  if (_invoke) return _invoke;
  if (window.__TAURI__) {
    const mod = await import("@tauri-apps/api/core");
    _invoke = mod.invoke;
  }
  return _invoke;
}

// Per-launch API token. The Tauri shell generates it, passes it to the backend, and hands it to
// the page through the get_api_token command (more reliable than a variable injected into the
// page, which a reload would lose). It is "" in dev mode, where the backend is open.
let _token = null;

export async function getApiToken() {
  if (_token !== null) return _token;
  let token = "";
  if (isTauri()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      token = (await invoke("get_api_token")) || "";
    } catch { /* older shell without the command: backend is open */ }
  } else {
    token = window.__AVIO_TOKEN__ || "";
  }
  _token = token;
  return _token;
}

// Header to add to every direct fetch() to the backend.
export async function authHeaders() {
  const t = await getApiToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const t0 = performance.now();
  debugLog(`→ ${method} ${path}`, "start");
  try {
    const res = await apiRaw(path, opts);
    debugLog(`← ${method} ${path} OK (${((performance.now() - t0) / 1000).toFixed(1)}s)`, "done");
    return res;
  } catch (e) {
    const firstLine = String(e?.message || e).split("\n")[0];
    debugLog(`← ${method} ${path} FAILED (${((performance.now() - t0) / 1000).toFixed(1)}s): ${firstLine}`, "error", { reveal: false });
    throw e;
  }
}

// Same as api() without the debug-log entries, for polling loops.
export function apiQuiet(path, opts = {}) {
  return apiRaw(path, opts);
}

/**
 * Resolve once the backend answers /api/health. Never rejects and never shows an
 * error: the backend may still be starting, or restarting after "Restart Backend".
 * onWaiting() fires once if the first ping fails. shouldStop() aborts the wait
 * (returns false in that case). Health pings are not written to the debug log.
 */
export async function waitForBackend({ onWaiting, onSlow, slowAfterMs = 60000, shouldStop, intervalMs = 500 } = {}) {
  const t0 = Date.now();
  let notified = false;
  let slowNotified = false;
  for (;;) {
    if (shouldStop?.()) return false;
    try {
      await apiRaw("/api/health");
      return true;
    } catch {
      if (!notified) { notified = true; onWaiting?.(); }
      if (!slowNotified && Date.now() - t0 >= slowAfterMs) { slowNotified = true; onSlow?.(); }
      await new Promise(r => setTimeout(r, intervalMs));
    }
  }
}

async function apiRaw(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const invoke = await getInvoke();

  // ── Tauri path: proxy through Rust commands (no CSP) ──────────────────────
  if (invoke) {
    try {
      if (method === "GET") {
        return await invoke("api_get", { path });
      } else {
        const body = opts.body ? JSON.parse(opts.body) : {};
        return await invoke("api_post", { path, body });
      }
    } catch (e) {
      const msg = String(e);
      if (msg.includes("Request failed") || msg.includes("Connection refused")) {
        throw new Error(
          `Cannot reach the backend server.\n` +
          `Start it with: npm run dev:backend\n` +
          `Detail: ${msg}`
        );
      }
      throw new Error(msg);
    }
  }

  // ── Browser / plain fetch fallback ────────────────────────────────────────
  const port = window.__SF_BACKEND_PORT__ || 7891;
  const url  = `http://localhost:${port}${path}`;
  let res;
  try {
    const headers = { "Content-Type": "application/json", ...(await authHeaders()), ...(opts.headers || {}) };
    res = await fetch(url, { ...opts, headers });
  } catch (e) {
    throw new Error(
      `Cannot reach backend at ${url}\n` +
      `Make sure the Python backend is running: cd backend && .venv/bin/python main.py\n` +
      `Detail: ${e?.name}: ${e?.message}`
    );
  }
  if (!res.ok) {
    let body = "";
    try { body = await res.text(); } catch {}
    let detail = body;
    let code;
    try { const j = JSON.parse(body); detail = j?.detail || body; code = j?.code; } catch {}
    if (code === "session_expired") throw new Error(detail);
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${path}\n${detail}`);
  }
  return res.json();
}

// onTruncated() fires (before onDone) when the model stopped because it hit its token
// limit, i.e. the answer is incomplete. onSkills(names) fires first with the skills the
// backend actually injected into the prompt (an empty array when none).
// The reply being streamed for each AI surface ("apex", "soql", "chat"), so the Stop button can reach it
// from anywhere (the panel that started it may have been unmounted by a tab switch).
const running = new Map();   // surface -> { controller, requestId, stopped }

function newRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

// Stop the reply being streamed for `surface`: the browser request is aborted (the UI is free at once) and
// the backend is told to close the provider connection, so the provider stops generating. None of the
// callbacks of that apiStream() call fire afterwards: the caller keeps what it already received.
// Returns false when nothing was running.
export function stopStream(surface) {
  const r = running.get(surface);
  if (!r) return false;
  running.delete(surface);
  r.stopped = true;
  r.controller.abort();
  apiQuiet("/api/ai/chat/cancel", { method: "POST", body: JSON.stringify({ request_id: r.requestId }) }).catch(() => {});
  return true;
}

// opts.surface: "apex" | "soql" | "chat". Gives the request an id and makes it stoppable with stopStream().
export async function apiStream(path, body, onDelta, onDone, onError, onTruncated, onSkills, opts = {}) {
  // Streaming SSE must use fetch directly (Tauri IPC doesn't support streaming)
  const port = window.__SF_BACKEND_PORT__ || 7891;
  const url  = `http://localhost:${port}${path}`;
  const surface = opts.surface;
  const handle = surface ? { controller: new AbortController(), requestId: newRequestId(), stopped: false } : null;
  if (handle) {
    const prev = running.get(surface);             // never two live replies for one surface
    if (prev) { prev.stopped = true; prev.controller.abort(); }
    running.set(surface, handle);
    body = { ...body, request_id: handle.requestId };
  }
  try {
    let res;
    try {
      res = await fetch(url, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...(await authHeaders()) },
        body:    JSON.stringify(body),
        signal:  handle?.controller.signal,
      });
    } catch (e) {
      if (handle?.stopped) return;
      onError(`Cannot reach backend: ${e?.message}`);
      return;
    }
    if (!res.ok) {
      const text = await res.text();
      let msg = text;
      try { msg = JSON.parse(text)?.detail || text; } catch {}
      onError(msg);
      return;
    }
    const reader = res.body.getReader();
    const dec    = new TextDecoder();
    let buf = "";
    while (true) {
      let chunk;
      try {
        chunk = await reader.read();
      } catch (e) {
        if (handle?.stopped) return;               // Stop was pressed: not an error
        throw e;
      }
      const { done, value } = chunk;
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") { onDone(); return; }
        try {
          const obj = JSON.parse(payload);
          if (obj.error) { onError(obj.error); return; }
          if (obj.truncated) onTruncated?.();
          if (Array.isArray(obj.skills)) onSkills?.(obj.skills);
          if (obj.delta) onDelta(obj.delta);
        } catch {}
      }
    }
    onDone();
  } finally {
    if (handle && running.get(surface) === handle) running.delete(surface);
  }
}

// isLocalUrl lives in its own module so the node tests can import it without the Tauri imports.
export { isLocalUrl } from "./localUrl.js";

// window.__TAURI__ only exists when app.withGlobalTauri is true (it is not), so
// check __TAURI_INTERNALS__, which Tauri v2 always injects.
export function isTauri() {
  return typeof window !== "undefined" && !!(window.__TAURI_INTERNALS__ || window.__TAURI__);
}

// Open a URL in the user's default browser. A plain <a target="_blank"> does nothing in the
// packaged WebView, so go through the Tauri shell plugin (https:// links only).
export async function openExternal(url) {
  if (isTauri()) {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

// Resolves to the chosen folder, or null if the user cancelled. Throws if the
// native dialog is unavailable or fails, so callers can show an error.
export async function openDirDialog() {
  if (isTauri()) {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const result = await open({ directory: true });
    return result || null;
  }
  // Browser/dev mode — prompt for a path via simple text input
  const path = window.prompt("Enter output folder path (leave blank for ~/Downloads):");
  if (path === null) return null;          // user clicked Cancel
  return path.trim() || "__default__";    // blank → default
}

// Resolves to the chosen path, or null if the user cancelled. Throws if the
// native dialog is unavailable or fails (never returns null for that).
export async function openSaveDialog(opts = {}) {
  if (!isTauri()) throw new Error("The native Save dialog is only available in the desktop app.");
  const { save } = await import("@tauri-apps/plugin-dialog");
  return (await save(opts)) || null;
}
