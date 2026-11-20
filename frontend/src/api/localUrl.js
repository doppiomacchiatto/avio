// True for a local model server (Ollama, LM Studio, ...), which usually has a small context window.
// Mirrors is_local_url() in backend/ai_client.py (keep the two in step): localhost, 127.0.0.1, ::1,
// private / link-local IPs, *.local / *.lan / *.internal / *.home.arpa (host.docker.internal),
// single-label names, or port 11434 / 1234 on a host that is not a built-in cloud provider.
// A saved connection's own "local" flag (from the backend) beats this; see useConnectionChoice.
const CLOUD_HOSTS = new Set([
  "opencode.ai", "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
  "openrouter.ai", "eu.openrouter.ai", "us.openrouter.ai", "api.groq.com",
]);
export function isLocalUrl(url) {
  let u;
  try { u = new URL(String(url || "").trim()); } catch { return false; }
  if (!/^https?:$/.test(u.protocol)) return false;
  const host = u.hostname.toLowerCase().replace(/\.$/, "").replace(/^\[|\]$/g, "");
  if (!host) return false;
  if (host === "localhost" || /\.(local|lan|internal|home\.arpa|localhost)$/.test(host)) return true;
  const v4 = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (v4) {
    const [a, b] = [Number(v4[1]), Number(v4[2])];
    if (host === "127.0.0.1" || a === 10 || (a === 172 && b >= 16 && b <= 31) ||
        (a === 192 && b === 168) || (a === 169 && b === 254)) return true;
  } else if (host.includes(":")) {
    if (host === "::1" || /^f[cd][0-9a-f]{2}:/.test(host) || /^fe[89ab][0-9a-f]:/.test(host)) return true;
  } else if (!host.includes(".")) {
    return true;                       // single-label name: only resolvable on the LAN / in Docker
  }
  return (u.port === "11434" || u.port === "1234") && !CLOUD_HOSTS.has(host);
}
