// Shared helpers for AI chat replies (Apex Runner, SOQL Runner).

// Split a reply into text and fenced code blocks. Each code block carries its language tag
// (lower-cased, "" when none) so callers can tell Apex from the ```xml meta file or JSON
// that models often add. A tag only counts when the fence line ends right after it, so a
// one-line ```SELECT Id FROM Account``` is not mistaken for a block tagged "SELECT".
// An unclosed fence (a cut-off reply) stays plain text.
export function parseBlocks(text) {
  const parts = [];
  const re = /```(?:([A-Za-z0-9_+#.-]+)[ \t]*\r?\n|\r?\n?)([\s\S]*?)```/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ type: "text", content: text.slice(last, m.index) });
    parts.push({ type: "code", lang: (m[1] || "").toLowerCase(), content: m[2].trimEnd() });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ type: "text", content: text.slice(last) });
  return parts;
}

// Languages whose blocks can be inserted into the Apex / SOQL editors.
export const APEX_LANGS = ["", "apex", "java", "javascript", "js", "cls", "trigger"];
export const SOQL_LANGS = ["", "soql", "sql", "sosl"];

export function isLang(lang, allowed) {
  return allowed.includes(String(lang || "").toLowerCase());
}

// Sent when the user clicks "Continue" on a reply that hit the token limit.
export const CONTINUE_PROMPT = "Continue exactly where you stopped. Do not repeat anything you already wrote.";
