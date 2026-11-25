// Record Counts: one SELECT COUNT() per object, used by the SOQL Runner's Counts button and the AI Chat's
// Record Counts action. Plain functions with the query runner passed in, so node tests can drive them.

export const COUNT_OBJECTS = ["Account", "Contact", "Lead", "Opportunity", "Case", "Task", "Event", "User"];
export const MAX_CUSTOM_COUNTS = 20;   // custom objects (__c) counted at most, so a big org stays a few dozen calls
export const COUNT_CONCURRENCY = 4;

// The objects to count: the core list plus up to MAX_CUSTOM_COUNTS custom objects from the org's object list.
export function countTargets(objects) {
  const custom = (objects || []).map((o) => o?.apiName).filter((n) => typeof n === "string" && n.endsWith("__c"));
  return [...new Set([...COUNT_OBJECTS, ...custom.slice(0, MAX_CUSTOM_COUNTS)])];
}

// Runs the counts, `concurrency` at a time. runQuery(soql) resolves to the /api/soql reply ({ totalSize }).
// A failed object gets count -1 and its error; the others still run. Sorted by count (largest first), then name.
export async function countRecords(names, runQuery, { concurrency = COUNT_CONCURRENCY } = {}) {
  const out = [];
  let next = 0;
  async function worker() {
    while (next < names.length) {
      const name = names[next++];
      try {
        const d = await runQuery(`SELECT COUNT() FROM ${name}`);
        out.push({ name, count: Number.isInteger(d?.totalSize) ? d.totalSize : 0, error: "" });
      } catch (e) {
        out.push({ name, count: -1, error: String(e?.message || e || "failed") });
      }
    }
  }
  await Promise.all(Array.from({ length: Math.max(1, Math.min(concurrency, names.length)) }, worker));
  return out.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

// True when a typed chat message asks for the org-wide record counts ("record counts", "top objects by record
// count", "how many records are in each object"). The chat then runs the counts instead of asking the model,
// which can only write queries. A question about one object's data ("count the Accounts in Texas") is left
// to the model.
export function isRecordCountsRequest(text) {
  const t = String(text || "").toLowerCase().replace(/\s+/g, " ").trim();
  if (!t || t.length > 400) return false;
  return /\brecord ?counts?\b/.test(t)
    || /\b(count|counting) (all |the )?(of )?records\b/.test(t)
    || /\bhow many records\b.*\b(each|every|per|all|by) (object|objects|sobject)/.test(t)
    || /\b(top|largest|biggest) objects\b.*\b(records?|volume|count)/.test(t)
    || /\bobjects? by (record )?(count|volume)\b/.test(t)
    || /\brecord volumes?\b/.test(t);
}

// Totals and shares for the chat report.
export function summarizeCounts(results) {
  const ok = results.filter((r) => r.count >= 0);
  const total = ok.reduce((n, r) => n + r.count, 0);
  const rows = results.map((r) => ({ ...r, share: r.count >= 0 && total > 0 ? r.count / total : 0 }));
  return {
    rows,
    total,
    counted: ok.length,
    failed: results.length - ok.length,
    empty: ok.filter((r) => r.count === 0).length,
    custom: ok.filter((r) => r.name.endsWith("__c")).reduce((n, r) => n + r.count, 0),
  };
}

const fmt = (n) => n.toLocaleString("en-US");
const pct = (x) => (x * 100).toFixed(x >= 0.1 ? 0 : 1) + "%";

// The report as plain text: what the chat shows if the table cannot be drawn (a reopened saved chat) and what
// the AI reads on the next turn, so follow-up questions about the numbers work.
export function recordCountsText(alias, summary) {
  const { rows, total, counted, failed, empty, custom } = summary;
  const top = rows.filter((r) => r.count > 0).slice(0, 3).map((r) => `${r.name} ${fmt(r.count)} (${pct(r.share)})`);
  const lines = [
    `📊 **Record Counts** for ${alias}: ${fmt(total)} records across ${counted} object${counted === 1 ? "" : "s"}` +
      (failed ? ` (${failed} could not be counted)` : "") + ".",
  ];
  if (top.length) lines.push(`Largest: ${top.join(", ")}.`);
  if (custom) lines.push(`Custom objects hold ${fmt(custom)} of them (${pct(custom / total)}).`);
  if (empty) lines.push(`${empty} object${empty === 1 ? " is" : "s are"} empty.`);
  lines.push("");
  for (const r of rows) {
    lines.push(r.count < 0 ? `${r.name}: not counted (${r.error.slice(0, 120)})` : `${r.name}: ${fmt(r.count)}`);
  }
  return lines.join("\n");
}

export const formatCount = fmt;
export const formatShare = pct;
