import { pathToFileURL, fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../../frontend/src/", import.meta.url));
const { buildChatSystem } = await import(pathToFileURL(root + "chatSystem.js").href);

let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + detail.slice(0, 400) : "")); };

const org = { alias: "demo-org", username: "someone@example.com" };
const empty = { objects: [], fields: {}, objectsLoading: false, objectsLoaded: false };

// ---- no org ----------------------------------------------------------------------------------------
let s = buildChatSystem(null, empty);
check("no org: says none is selected and to click Select Org only for org questions",
  s.includes("No Salesforce org is selected") && s.includes("Select Org") && s.includes("general Salesforce questions"), s);
check("no org: does not pretend to know an org or objects", !s.includes("connected to the Salesforce org") && !s.includes("[SELECT_OBJECT"), s);

// ---- org connected, objects not there yet (the bug in the screenshot) -----------------------------------
for (const [name, ctx] of [["loading", { ...empty, objectsLoading: true }], ["not started", empty], ["ctx missing", undefined]]) {
  s = buildChatSystem(org, ctx);
  check(`org + ${name}: names the org`, s.includes('"demo-org"'), s);
  check(`org + ${name}: says the list is still loading and forbids claiming no org`,
    s.includes("still loading") && s.includes("do NOT say that no org is connected"), s);
  check(`org + ${name}: tells the user to retry for object questions`, s.includes("try again in a few seconds"), s);
  check(`org + ${name}: never uses the old misleading line or tells them to select an org`,
    !s.includes("No objects loaded") && !s.includes("select an org first") && !s.includes("Select Org"), s);
  check(`org + ${name}: no object list or tag instruction yet`, !s.includes("[SELECT_OBJECT") && !s.includes("1. "), s);
}

// ---- loaded but empty --------------------------------------------------------------------------------------
s = buildChatSystem(org, { ...empty, objectsLoaded: true });
check("loaded but empty: says so, still allows general questions", s.includes("returned no objects") && s.includes("general Salesforce questions") && !s.includes("still loading"), s);

// ---- loaded with objects -----------------------------------------------------------------------------------
const objs = [{ apiName: "Account", label: "Account" }, { apiName: "Invoice__c", label: "Invoice" }];
s = buildChatSystem(org, { ...empty, objects: objs, objectsLoaded: true });
check("objects: numbered exact API names with labels", s.includes("1. Account — Account") && s.includes("2. Invoice__c — Invoice"), s);
check("objects: keeps the SELECT_OBJECT tag instruction and exact-name rule", s.includes("[SELECT_OBJECT: ApiName__c]") && s.includes("exact API names"), s);
check("objects: names the org and does not say loading", s.includes('"demo-org"') && !s.includes("still loading"), s);
s = buildChatSystem(org, { ...empty, objects: objs, objectsLoading: true });
check("objects present while a reload is flagged: uses the list", s.includes("2. Invoice__c — Invoice"), s);

const big = Array.from({ length: 1500 }, (_, i) => ({ apiName: `Obj${i}__c`, label: `Object ${i}` }));
s = buildChatSystem(org, { ...empty, objects: big, objectsLoaded: true });
check("a large org (1,500 objects) is handled, first and last present", s.includes("1. Obj0__c") && s.includes("1500. Obj1499__c"));

// ---- wording ------------------------------------------------------------------------------------------------
for (const [name, text] of [["no org", buildChatSystem(null, empty)], ["loading", buildChatSystem(org, empty)], ["loaded", buildChatSystem(org, { ...empty, objects: objs, objectsLoaded: true })]]) {
  check(`${name}: uses the current product name`, text.includes("Avio") && !text.includes("SF Metadata Explorer"), text);
}
check("org username is not put in the prompt", !buildChatSystem(org, empty).includes("someone@example.com"));

console.log("\nfailures:", fails);
process.exit(fails ? 1 : 0);
