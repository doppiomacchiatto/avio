// Saving, loading and tracking AI conversations.
//
// The three AI surfaces (Apex Runner, SOQL Runner, AI Chat) keep their messages in the session
// store (sessionStore.js), which lives until the app closes. This module adds three things:
//   1. unsaved tracking, so the close dialog can offer Save or Discard;
//   2. a file format (.json, and a readable .md export) for "Save as..." and "Load...";
//   3. strict validation: a file is untrusted input, and what is loaded becomes model context.
// Saved conversations kept for the next launch live in the backend (chat_store.py, 3 days).
import { getSession, setSession } from "./sessionStore.js";

export const FORMAT_VERSION = 1;
export const RETENTION_DAYS = 3;                 // mirrors chat_store.RETENTION_DAYS (the backend enforces it)
export const MAX_MESSAGES   = 500;
export const MAX_CHARS      = 2_000_000;
export const MAX_FILE_CHARS = 5_000_000;         // refuse bigger files before parsing them

export const SURFACES = {
  apex: { label: "Apex Runner", key: "apex.ai.messages" },
  soql: { label: "SOQL Runner", key: "soql.ai.messages" },
  chat: { label: "AI Chat",     key: "chat.messages"     },
};

const MAX_SKILLS = 20;
const MAX_SKILL_LEN = 100;

// Keep only user/assistant text and the skills a reply used. UI notices (`system: true`),
// other roles, non-string or empty content and unknown fields are dropped.
export function cleanMessages(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const m of list) {
    if (!m || typeof m !== "object" || m.system === true) continue;
    if ((m.role !== "user" && m.role !== "assistant") || typeof m.content !== "string" || !m.content.trim()) continue;
    const item = { role: m.role, content: m.content };
    if (m.role === "assistant" && Array.isArray(m.skills)) {
      const names = m.skills
        .filter((s) => typeof s === "string" && s.trim())
        .map((s) => s.slice(0, MAX_SKILL_LEN))
        .slice(0, MAX_SKILLS);
      if (names.length) item.skills = names;
    }
    out.push(item);
  }
  return out;
}

export function makeTitle(messages, given) {
  let text = String(given || "").trim();
  if (!text) text = messages.find((m) => m.role === "user")?.content || "";
  text = text.split(/\s+/).filter(Boolean).join(" ");
  return text.length > 60 ? text.slice(0, 60) + "..." : text;
}

// Rough size for the "will be sent with your next message" notice (about 4 characters a token).
export function estimateTokens(messages) {
  return Math.ceil(cleanMessages(messages).reduce((n, m) => n + m.content.length, 0) / 4);
}

// ---- file format -----------------------------------------------------------------------------------------

// No connection, URL or key is ever written: API keys never reach the page, and a saved file
// might be shared.
export function serializeChat(surface, messages, { appVersion = "", now = new Date() } = {}) {
  const clean = cleanMessages(messages);
  return {
    avio_chat: FORMAT_VERSION,
    surface,
    saved_at: now.toISOString(),
    app_version: String(appVersion || ""),
    title: makeTitle(clean),
    messages: clean,
  };
}

export function toMarkdown(chat) {
  const lines = [`# ${chat.title || "Avio conversation"}`, ""];
  const meta = [SURFACES[chat.surface]?.label, chat.saved_at ? `saved ${chat.saved_at}` : ""].filter(Boolean);
  if (meta.length) lines.push(`_${meta.join(", ")}_`, "");
  for (const m of chat.messages) {
    lines.push(m.role === "user" ? "## You" : "## AI", "", m.content.trimEnd(), "");
    if (m.skills?.length) lines.push(`_Skills used: ${m.skills.join(", ")}_`, "");
  }
  return lines.join("\n");
}

// Explains a file the user picked by name before it is read, or returns null if it may be a conversation.
// A Markdown export is for reading: it cannot be loaded back, so say so instead of "not valid JSON".
export function checkFileName(name) {
  if (/\.(md|markdown|txt)$/i.test(String(name || ""))) {
    return "That is a readable text export, which Avio cannot load back. To continue a conversation later, save it as .json (Save, then choose the Avio conversation type) and load that file.";
  }
  return null;
}

// Returns { ok: true, chat: { surface, title, savedAt, messages, ignored } } or { ok: false, error }.
// `ignored` counts entries that were dropped (UI notices, unknown roles, empty text).
export function parseChatFile(text) {
  if (typeof text !== "string") return { ok: false, error: "The file could not be read as text." };
  if (text.length > MAX_FILE_CHARS) return { ok: false, error: "That file is too large to be an Avio conversation." };
  let data;
  try {
    data = JSON.parse(text.replace(/^\uFEFF/, ""));
  } catch {
    return { ok: false, error: "That file is not an Avio conversation (it is not valid JSON). Use a .json file saved from Avio." };
  }
  if (!data || typeof data !== "object" || Array.isArray(data) || typeof data.avio_chat !== "number") {
    return { ok: false, error: "That file is not an Avio conversation." };
  }
  if (data.avio_chat !== FORMAT_VERSION) {
    return { ok: false, error: data.avio_chat > FORMAT_VERSION
      ? "That conversation was saved by a newer version of Avio. Update Avio to open it."
      : "That conversation uses an old format this version cannot open." };
  }
  if (!Array.isArray(data.messages)) return { ok: false, error: "The file has no messages." };
  if (data.messages.length > MAX_MESSAGES) {
    return { ok: false, error: `That conversation has more than ${MAX_MESSAGES} messages, which is more than Avio loads.` };
  }
  const messages = cleanMessages(data.messages);
  if (messages.length === 0) return { ok: false, error: "The file has no messages Avio can use." };
  if (messages.reduce((n, m) => n + m.content.length, 0) > MAX_CHARS) {
    return { ok: false, error: "That conversation is too long to load." };
  }
  return {
    ok: true,
    chat: {
      surface: Object.hasOwn(SURFACES, data.surface) ? data.surface : null,
      title: makeTitle(messages, typeof data.title === "string" ? data.title : ""),
      savedAt: typeof data.saved_at === "string" ? data.saved_at : "",
      messages,
      ignored: data.messages.length - messages.length,
    },
  };
}

export function defaultFileName(surface, ext, now = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}`;
  return `avio-${surface}-${stamp}.${ext}`;
}

// "replace" drops the current conversation, "append" adds the loaded one after it.
export function mergeMessages(existing, incoming, mode) {
  const base = mode === "append" ? cleanMessages(existing) : [];
  const merged = [...base, ...incoming];
  return merged.length > MAX_MESSAGES ? merged.slice(merged.length - MAX_MESSAGES) : merged;
}

// ---- unsaved tracking --------------------------------------------------------------------------------------
// A conversation counts as saved while its messages are the very array that was last saved (or
// loaded). Panels always replace the array on a change, so a new message makes it unsaved again.
const saved = new Map();   // surface -> the messages array that was saved

export const getMessages = (surface) => getSession(SURFACES[surface].key, []);

export function markSaved(surface, messages = getMessages(surface)) {
  saved.set(surface, messages);
}

export function forgetSaved() {
  saved.clear();
}

export function unsavedChats() {
  const out = [];
  for (const [surface, def] of Object.entries(SURFACES)) {
    const messages = getSession(def.key, []);
    if (messages === saved.get(surface)) continue;
    const count = cleanMessages(messages).length;
    if (count > 0) out.push({ surface, label: def.label, count });
  }
  return out;
}

export function hasUnsavedChats() {
  return unsavedChats().length > 0;
}

// Put messages into a panel. `markAsSaved` is true when they came from storage (a restore or a
// file load that replaced everything), so closing right afterwards does not nag.
export function setMessages(surface, messages, { markAsSaved = false } = {}) {
  setSession(SURFACES[surface].key, messages);
  if (markAsSaved) markSaved(surface, messages);
}

export function loadIntoSurface(surface, incoming, mode) {
  const merged = mergeMessages(getMessages(surface), incoming, mode);
  setMessages(surface, merged, { markAsSaved: mode === "replace" });
  return merged;
}

export function resetSurface(surface) {
  setSession(SURFACES[surface].key, []);
  saved.delete(surface);
}

// Save every unsaved conversation to the app-data folder through `post(path, body)` (the api
// client's POST). Surfaces that saved are marked saved; the others are returned in `failed`.
// `only` limits it to some surfaces (for example ["chat"]).
export async function saveUnsavedToApp(post, only = null) {
  const savedList = [], failed = [];
  for (const u of unsavedChats()) {
    if (only && !only.includes(u.surface)) continue;
    const messages = getMessages(u.surface);
    try {
      await post("/api/chats", { surface: u.surface, messages: cleanMessages(messages) });
      markSaved(u.surface, messages);
      savedList.push(u);
    } catch (e) {
      failed.push({ ...u, error: String(e?.message || e) });
    }
  }
  return { saved: savedList, failed };
}
