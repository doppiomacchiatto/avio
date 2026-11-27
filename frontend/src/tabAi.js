// What the AI panel on the FLS Explorer, Profiles & PermSets and REST Explorer tabs knows and offers.
// Each build*System function turns what the tab shows right now into the system prompt; long lists are capped
// so a big object or response does not fill the model's context. Pure functions (tested in test_tabai.mjs).

const HEAD = "You are a Salesforce expert assistant embedded in Avio, a Salesforce metadata tool.";
export const MAX_FIELDS = 300;          // fields / field permissions listed in full
export const MAX_RULES = 50;            // validation rules listed
export const MAX_FORMULA = 600;         // characters of one validation rule formula
export const MAX_RESPONSE_CHARS = 8000; // characters of a REST response body
export const MAX_REQUEST_BODY = 4000;   // characters of a REST request body

const orgLine = (org) => org
  ? `The user is connected to the Salesforce org "${org.alias}".`
  : "No Salesforce org is selected right now. If the user asks about their own org's data, tell them to click Select Org first.";

function capped(list, max, render) {
  const lines = list.slice(0, max).map(render);
  if (list.length > max) lines.push(`… and ${list.length - max} more (not shown).`);
  return lines.join("\n");
}

const clip = (s, max) => {
  const t = String(s ?? "");
  return t.length > max ? t.slice(0, max) + ` … [cut, ${t.length - max} more characters]` : t;
};

// ── FLS Explorer ──────────────────────────────────────────────────────────────────────────────────────

export const FLS_CHIPS = [
  { label: "📋 Summarize fields",  prompt: "Summarize this object's fields: what the custom fields are for, which are required, and anything unusual about their types." },
  { label: "🔒 Security review",   prompt: "Review the field-level access shown here. Which fields look sensitive, and are any of them readable or editable when they probably should not be?" },
  { label: "⚡ Explain rules",     prompt: "Explain each validation rule in plain language: when it fires and what it blocks. Point out any rule that looks wrong or fragile." },
  { label: "✍️ Write SOQL",        prompt: "Write a SOQL query for this object that selects its most useful fields." },
];

// fields: [{ label, apiName, type, required, readable, editable }]  (readable/editable are the connected user's access)
// rules:  [{ name, active, errorField, errorMessage, errorConditionFormula, description }]
export function buildFlsSystem({ org, object, fields = [], rules = [], rulesLoaded = false, exportSelection = [] }) {
  const lines = [HEAD, "The user is on the FLS Explorer tab, which shows an object's fields and validation rules.", orgLine(org)];
  if (!object) {
    lines.push("No object is selected yet. If the user asks about one, tell them to pick it in the sidebar and click Load Fields.");
  } else {
    lines.push(`Selected object: ${object.label} (${object.apiName}).`);
    if (!fields.length) {
      lines.push("Its fields are not loaded yet. If the user asks about them, tell them to click Load Fields.");
    } else {
      lines.push(
        "",
        `Fields (${fields.length}). Readable and Editable are the access of the user Avio is connected as, from the object describe; they are not a profile's settings (the Profiles & PermSets tab shows those).`,
        "Format: API name | label | type | required | readable | editable",
        capped(fields, MAX_FIELDS, (f) =>
          `${f.apiName} | ${f.label} | ${f.type} | ${f.required ? "required" : "-"} | ${f.readable ? "R" : "-"} | ${f.editable ? "E" : "-"}`),
      );
    }
    if (rules.length) {
      lines.push(
        "",
        `Validation rules (${rules.length}):`,
        capped(rules, MAX_RULES, (r) =>
          `- ${r.name} [${r.active ? "active" : "inactive"}] error on ${r.errorField || "page"}: "${r.errorMessage || ""}"` +
          (r.errorConditionFormula ? `\n  formula: ${clip(r.errorConditionFormula, MAX_FORMULA)}` : "")),
      );
    } else if (rulesLoaded) {
      lines.push("", "This object has no validation rules.");
    } else if (fields.length) {
      lines.push("", "Validation rules are not loaded. If the user asks about them, tell them to open the Validation Rules panel under the fields.");
    }
  }
  if (exportSelection.length) lines.push("", `Objects checked for Excel export: ${exportSelection.join(", ")}.`);
  lines.push(
    "",
    "You cannot change the org from here. To turn a validation rule on or off, the user uses the Enable / Disable buttons in the Validation Rules panel.",
    "When you write a query, wrap it in a ```soql code block. Be concise and direct.",
  );
  return lines.join("\n");
}

// ── Profiles & PermSets ───────────────────────────────────────────────────────────────────────────────

export const PROFILES_CHIPS = [
  { label: "📋 Summarize access",  prompt: "Summarize what this principal can do on this object: object permissions and field access." },
  { label: "⚠️ Risky permissions", prompt: "Point out risky permissions here, such as View All / Modify All or edit access to sensitive fields, and explain the risk." },
  { label: "🎯 Least privilege",   prompt: "Suggest a least-privilege setup for this access, for example what to move into a permission set or permission set group." },
  { label: "✍️ Audit SOQL",        prompt: "Write SOQL I can run to audit these permissions across the org (ObjectPermissions and FieldPermissions)." },
];

const OBJ_PERM_KEYS = [
  ["Read", "AllowRead"], ["Create", "AllowCreate"], ["Edit", "AllowEdit"],
  ["Delete", "AllowDelete"], ["View All", "ViewAllRecords"], ["Modify All", "ModifyAllRecords"],
];

// principal: { type: "profile" | "permset", name }
// flsData:   { obj_perms: {AllowRead...}, fls: { fieldName: { readable, editable } } }
export function buildProfilesSystem({ org, principal, object, flsData, profiles = [], permsets = [], checkedObjects = [] }) {
  const lines = [HEAD, "The user is on the Profiles & PermSets tab, which shows the object and field permissions a profile or permission set grants.", orgLine(org)];
  if (profiles.length) lines.push(`${profiles.length} profiles are loaded.`);
  if (permsets.length) lines.push(`${permsets.length} permission sets are loaded.`);
  if (!principal) {
    lines.push("No profile or permission set is selected. If the user asks about one, tell them to load and select it in the left sidebar.");
  } else {
    lines.push(`Selected ${principal.type === "profile" ? "profile" : "permission set"}: ${principal.name}.`);
    if (!object) {
      lines.push("No object is selected. If the user asks about an object's access, tell them to click it in the middle column.");
    } else if (!flsData) {
      lines.push(`Selected object: ${object.label} (${object.apiName}). Its permissions are not loaded yet.`);
    } else {
      const op = flsData.obj_perms || {};
      lines.push(
        `Selected object: ${object.label} (${object.apiName}).`,
        `Object permissions: ${OBJ_PERM_KEYS.map(([label, key]) => `${label}=${op[key] ? "yes" : "no"}`).join(", ")}.`,
      );
      const entries = Object.entries(flsData.fls || {});
      if (entries.length) {
        lines.push(
          "",
          `Field permissions (${entries.length}). Fields not listed have no FieldPermissions entry, which means no access (required and system fields are not listed).`,
          "Format: field | readable | editable",
          capped(entries, MAX_FIELDS, ([name, p]) => `${name} | ${p.readable ? "R" : "-"} | ${p.editable ? "E" : "-"}`),
        );
      } else {
        lines.push("", "There are no field permission entries for this principal on this object.");
      }
    }
  }
  if (checkedObjects.length) lines.push("", `Objects checked for Excel export: ${checkedObjects.join(", ")}.`);
  lines.push(
    "",
    "You cannot change permissions from here; give the steps in Setup (or metadata the user can deploy) instead.",
    "When you write a query, wrap it in a ```soql code block. Be concise and direct.",
  );
  return lines.join("\n");
}

// ── REST Explorer ─────────────────────────────────────────────────────────────────────────────────────

export const REST_CHIPS = [
  { label: "✨ Explain response", prompt: "Explain this response: what it contains and anything notable in it." },
  { label: "🔧 Fix error",        prompt: "The last request failed. Explain why and give me a corrected request." },
  { label: "➡️ Next call",        prompt: "Suggest useful follow-up requests based on this response." },
  { label: "✍️ Build request",    prompt: "Build a REST request for me. Ask what I want to do if it is not clear." },
];

export const REQUEST_LANGS = ["http", "rest"];

// request:  { method, path, body }      response: { status, headers, body } | null      history: [{ method, path }]
export function buildRestSystem({ org, request, response, history = [] }) {
  const lines = [HEAD, "The user is on the REST Explorer tab, which sends requests to the Salesforce REST API (paths relative to the org, such as /services/data/v68.0/sobjects).", orgLine(org)];
  if (request) {
    lines.push("", `Current request in the editor: ${request.method} ${request.path}`);
    if (["POST", "PUT", "PATCH"].includes(request.method) && String(request.body || "").trim()) {
      lines.push("Request body:", clip(request.body, MAX_REQUEST_BODY));
    }
  }
  if (response) {
    const text = typeof response.body === "string" ? response.body : JSON.stringify(response.body, null, 2);
    lines.push(
      "",
      response.status ? `Last response: HTTP ${response.status}${response.headers?.["content-type"] ? ` (${response.headers["content-type"]})` : ""}` : "Last request failed before a response arrived.",
      "Response body:",
      clip(text, MAX_RESPONSE_CHARS),
    );
  } else {
    lines.push("", "No request has been executed yet.");
  }
  if (history.length) {
    lines.push("", "Recent requests:", history.slice(0, 5).map((h) => `- ${h.method} ${h.path}`).join("\n"));
  }
  lines.push(
    "",
    "When you propose a request, put it in a ```http code block: the first line is the method and the path (for example GET /services/data/v68.0/sobjects/Account/describe); for POST, PUT or PATCH add a blank line and then the JSON body.",
    "Avio shows a Use Request button on that block, which only fills in the editor: the user still clicks Execute. Warn clearly before any request that changes or deletes data.",
    "Be concise and direct.",
  );
  return lines.join("\n");
}

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];

// Reads a ```http block back into { method, path, body }, or null if it is not one. Accepts a full URL (the
// host is dropped, since the REST Explorer adds the org's own) and an "HTTP/1.1" suffix; header lines between
// the request line and the blank line are ignored.
export function parseRequest(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const first = lines.findIndex((l) => l.trim());
  if (first < 0) return null;
  const m = lines[first].trim().match(/^([A-Za-z]+)\s+(\S+)(?:\s+HTTP\/[\d.]+)?$/);
  if (!m) return null;
  const method = m[1].toUpperCase();
  if (!METHODS.includes(method)) return null;
  let path = m[2].replace(/^https?:\/\/[^/]+/i, "");
  if (!path.startsWith("/")) return null;
  const blank = lines.findIndex((l, i) => i > first && !l.trim());
  const body = blank < 0 ? "" : lines.slice(blank + 1).join("\n").trim();
  return { method, path, body };
}
