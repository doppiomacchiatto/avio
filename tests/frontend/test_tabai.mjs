// tabAi.js: the system prompts and the ```http request parser of the AI panels on FLS Explorer,
// Profiles & PermSets and REST Explorer.
import { pathToFileURL, fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../../frontend/src/", import.meta.url));
const T = await import(pathToFileURL(root + "tabAi.js").href);
const { SURFACES } = await import(pathToFileURL(root + "chatHistory.js").href);

let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + String(detail).slice(0, 300) : "")); };
const org = { alias: "dev-org" };

// ── surfaces ──
for (const s of ["fls", "profiles", "rest"]) {
  check(`surface ${s} is registered with its ${s}.ai.messages key`, SURFACES[s]?.key === `${s}.ai.messages`, JSON.stringify(SURFACES[s]));
}

// ── FLS ──
let sys = T.buildFlsSystem({ org: null });
check("fls: no org says so", sys.includes("No Salesforce org is selected") && sys.includes("No object is selected"));
sys = T.buildFlsSystem({ org, object: { label: "Account", apiName: "Account" } });
check("fls: object without fields asks for Load Fields", sys.includes('"dev-org"') && sys.includes("Account (Account)") && sys.includes("click Load Fields"));
const fields = [
  { label: "Name", apiName: "Name", type: "string", required: true, readable: true, editable: true },
  { label: "SSN", apiName: "SSN__c", type: "encryptedstring", required: false, readable: true, editable: false },
];
sys = T.buildFlsSystem({ org, object: { label: "Account", apiName: "Account" }, fields });
check("fls: fields listed with access flags", sys.includes("Name | Name | string | required | R | E") && sys.includes("SSN__c | SSN | encryptedstring | - | R | -"), sys);
check("fls: says the access is the connected user's, not a profile's", sys.includes("access of the user Avio is connected as"));
check("fls: rules not loaded yet points at the panel", sys.includes("open the Validation Rules panel"));
sys = T.buildFlsSystem({ org, object: { label: "Account", apiName: "Account" }, fields, rules: [], rulesLoaded: true });
check("fls: loaded with no rules says so", sys.includes("has no validation rules"));
sys = T.buildFlsSystem({ org, object: { label: "Account", apiName: "Account" }, fields,
  rules: [{ name: "Need_Phone", active: true, errorField: "Phone", errorMessage: "Phone required", errorConditionFormula: "ISBLANK(Phone)" }],
  rulesLoaded: true, exportSelection: ["Account", "Contact"] });
check("fls: rules listed with state, field, message and formula", sys.includes("- Need_Phone [active] error on Phone: \"Phone required\"") && sys.includes("formula: ISBLANK(Phone)"), sys);
check("fls: export selection listed", sys.includes("Objects checked for Excel export: Account, Contact."));
check("fls: says it cannot change the org", sys.includes("You cannot change the org from here"));
const many = Array.from({ length: T.MAX_FIELDS + 5 }, (_, i) => ({ label: `F${i}`, apiName: `F${i}__c`, type: "string" }));
sys = T.buildFlsSystem({ org, object: { label: "Big", apiName: "Big__c" }, fields: many });
check("fls: long field lists are capped", sys.includes(`F${T.MAX_FIELDS - 1}__c`) && !sys.includes(`F${T.MAX_FIELDS}__c |`) && sys.includes("… and 5 more"), sys.slice(-200));
sys = T.buildFlsSystem({ org, object: { label: "A", apiName: "A" }, fields, rules: [{ name: "R", active: false, errorConditionFormula: "x".repeat(T.MAX_FORMULA + 50) }] });
check("fls: a long formula is cut", sys.includes("[cut, 50 more characters]") && sys.includes("[inactive] error on page"));

// ── Profiles ──
sys = T.buildProfilesSystem({ org });
check("profiles: nothing selected", sys.includes("No profile or permission set is selected"));
sys = T.buildProfilesSystem({ org, principal: { type: "permset", name: "Sales_Ops" }, profiles: ["A", "B"], permsets: ["Sales_Ops"] });
check("profiles: principal named, counts given, asks for an object", sys.includes("Selected permission set: Sales_Ops.") && sys.includes("2 profiles are loaded.") && sys.includes("1 permission sets are loaded.") && sys.includes("click it in the middle column"));
sys = T.buildProfilesSystem({ org, principal: { type: "profile", name: "Admin" }, object: { label: "Case", apiName: "Case" }, flsData: null });
check("profiles: object without data says not loaded", sys.includes("Selected profile: Admin.") && sys.includes("Its permissions are not loaded yet."));
sys = T.buildProfilesSystem({ org, principal: { type: "profile", name: "Admin" }, object: { label: "Case", apiName: "Case" },
  flsData: { obj_perms: { AllowRead: true, AllowEdit: true, ModifyAllRecords: true }, fls: { Subject: { readable: true, editable: true }, Secret__c: { readable: true, editable: false } } },
  checkedObjects: ["Case"] });
check("profiles: object perms spelled out", sys.includes("Read=yes, Create=no, Edit=yes, Delete=no, View All=no, Modify All=yes"), sys);
check("profiles: field perms listed", sys.includes("Subject | R | E") && sys.includes("Secret__c | R | -"));
check("profiles: explains missing entries", sys.includes("Fields not listed have no FieldPermissions entry"));
sys = T.buildProfilesSystem({ org, principal: { type: "profile", name: "Admin" }, object: { label: "Case", apiName: "Case" }, flsData: { obj_perms: {}, fls: {} } });
check("profiles: empty fls says so", sys.includes("no field permission entries"));

// ── REST ──
sys = T.buildRestSystem({ org, request: { method: "GET", path: "/services/data/v68.0/", body: "" }, response: null });
check("rest: request shown, nothing executed", sys.includes("Current request in the editor: GET /services/data/v68.0/") && sys.includes("No request has been executed yet."));
check("rest: GET body is not sent", !sys.includes("Request body:"));
check("rest: tells the model the http block format and that Execute stays manual", sys.includes("```http code block") && sys.includes("the user still clicks Execute"));
sys = T.buildRestSystem({ org, request: { method: "POST", path: "/services/data/v68.0/sobjects/Account", body: '{"Name":"X"}' },
  response: { status: 400, headers: { "content-type": "application/json" }, body: [{ errorCode: "REQUIRED_FIELD_MISSING" }] },
  history: [{ method: "GET", path: "/a" }, { method: "GET", path: "/b" }] });
check("rest: POST body, status, content type, body and history", sys.includes('Request body:\n{"Name":"X"}') && sys.includes("Last response: HTTP 400 (application/json)") && sys.includes("REQUIRED_FIELD_MISSING") && sys.includes("- GET /a"), sys);
sys = T.buildRestSystem({ org, request: { method: "GET", path: "/x" }, response: { status: 200, headers: {}, body: "y".repeat(T.MAX_RESPONSE_CHARS + 10) } });
check("rest: a big response is cut", sys.includes("[cut, 10 more characters]"));
sys = T.buildRestSystem({ org, request: { method: "GET", path: "/x" }, response: { status: 0, headers: {}, body: { error: "boom" } } });
check("rest: a failed request is described", sys.includes("Last request failed before a response arrived.") && sys.includes("boom"));

// ── parseRequest ──
const P = T.parseRequest;
check("parse: GET line", JSON.stringify(P("GET /services/data/v68.0/limits")) === JSON.stringify({ method: "GET", path: "/services/data/v68.0/limits", body: "" }));
check("parse: lower-case method, HTTP/1.1 suffix", P("get /a HTTP/1.1")?.method === "GET" && P("get /a HTTP/1.1")?.path === "/a");
let r = P('POST /services/data/v68.0/sobjects/Account\nContent-Type: application/json\n\n{\n  "Name": "Acme"\n}');
check("parse: POST with a header line and a body", r?.method === "POST" && r.body === '{\n  "Name": "Acme"\n}', JSON.stringify(r));
r = P("PATCH https://my.salesforce.com/services/data/v68.0/sobjects/Account/001\r\n\r\n{\"Name\":\"B\"}");
check("parse: full URL loses its host, CRLF handled", r?.path === "/services/data/v68.0/sobjects/Account/001" && r.body === '{"Name":"B"}', JSON.stringify(r));
check("parse: leading blank lines skipped", P("\n\nDELETE /x")?.method === "DELETE");
check("parse: not a request", P("SELECT Id FROM Account") === null && P("") === null && P("FETCH /x") === null && P("GET relative/path") === null);

console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
