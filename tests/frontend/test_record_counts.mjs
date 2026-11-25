// Record Counts logic shared by the SOQL Runner's Counts button and the AI Chat's Record Counts action.
import { pathToFileURL, fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../../frontend/src/", import.meta.url));
const RC = await import(pathToFileURL(root + "data/recordCounts.js").href);
const { COUNT_OBJECTS, MAX_CUSTOM_COUNTS, countTargets, countRecords, summarizeCounts, recordCountsText } = RC;

let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + String(detail).slice(0, 400) : "")); };

// ---- which objects ------------------------------------------------------------------------------------
check("core list: 8 objects incl. User", COUNT_OBJECTS.length === 8 && COUNT_OBJECTS.includes("User"), COUNT_OBJECTS);
check("no object list: just the core objects", JSON.stringify(countTargets(undefined)) === JSON.stringify(COUNT_OBJECTS));
const objs = [{ apiName: "Account" }, { apiName: "Invoice__c" }, { apiName: "Foo__mdt" }, { apiName: "Ship__c" }, {}, null, { apiName: 5 }];
const t = countTargets(objs);
check("custom objects added after the core ones, no duplicates, non-__c skipped",
  JSON.stringify(t) === JSON.stringify([...COUNT_OBJECTS, "Invoice__c", "Ship__c"]), t);
const many = Array.from({ length: 35 }, (_, i) => ({ apiName: `C${String(i).padStart(2, "0")}__c` }));
const capped = countTargets(many);
check(`cap: more than ${MAX_CUSTOM_COUNTS} custom objects -> only ${MAX_CUSTOM_COUNTS} queried`,
  capped.length === COUNT_OBJECTS.length + MAX_CUSTOM_COUNTS && capped.at(-1) === "C19__c" && !capped.includes("C20__c"), capped.length);

// ---- running them ---------------------------------------------------------------------------------------
const COUNTS = { Account: 500, Contact: 1200, Lead: 0, Opportunity: 300, Case: 300, Task: 4000, Event: 10, User: 25, Invoice__c: 2000 };
let inFlight = 0, peak = 0;
const asked = [];
async function runQuery(q) {
  asked.push(q);
  inFlight++; peak = Math.max(peak, inFlight);
  await new Promise((r) => setTimeout(r, 5));
  inFlight--;
  const name = q.replace("SELECT COUNT() FROM ", "");
  if (name === "Ship__c") throw new Error("sObject type 'Ship__c' is not supported.");
  return { records: [], totalSize: COUNTS[name] };
}
const res = await countRecords([...COUNT_OBJECTS, "Invoice__c", "Ship__c"], runQuery);
check("one COUNT() query per object", asked.length === 10 && asked.every((q) => /^SELECT COUNT\(\) FROM \w+$/.test(q)), asked);
check("at most 4 at a time", peak <= 4 && peak > 1, peak);
check("sorted by count, largest first; ties by name", res.map((r) => r.name).join(",") ===
  "Task,Invoice__c,Contact,Account,Case,Opportunity,User,Event,Lead,Ship__c", res.map((r) => r.name));
const ship = res.find((r) => r.name === "Ship__c");
check("a failed object gets -1 and its error; the rest still counted", ship.count === -1 && ship.error.includes("not supported")
  && res.filter((r) => r.count >= 0).length === 9, JSON.stringify(ship));
const odd = await countRecords(["A", "B"], async (q) => (q.endsWith("A") ? { totalSize: "7" } : {}));
check("a reply without an integer totalSize counts as 0", odd.every((r) => r.count === 0), JSON.stringify(odd));
check("no objects: empty result, no calls", (await countRecords([], () => { throw new Error("called"); })).length === 0);

// ---- the report ------------------------------------------------------------------------------------------
const s = summarizeCounts(res);
check("total adds up the counted objects only", s.total === 8335, s.total);
check("counted / failed / empty", s.counted === 9 && s.failed === 1 && s.empty === 1, JSON.stringify(s));
check("custom objects total", s.custom === 2000, s.custom);
check("shares: Task is 4000/8335", Math.abs(s.rows[0].share - 4000 / 8335) < 1e-9, s.rows[0].share);
check("shares of counted rows sum to 1", Math.abs(s.rows.filter((r) => r.count >= 0).reduce((n, r) => n + r.share, 0) - 1) < 1e-9);
check("all-zero org: shares are 0, no division by zero", summarizeCounts([{ name: "A", count: 0, error: "" }]).rows[0].share === 0);

const text = recordCountsText("org-one", s);
check("text: headline with total, objects and failures", text.startsWith("📊 **Record Counts** for org-one: 8,335 records across 9 objects (1 could not be counted)."), text);
check("text: the three largest with shares", text.includes("Largest: Task 4,000 (48%), Invoice__c 2,000 (24%), Contact 1,200 (14%)."), text);
check("text: custom share and empty objects", text.includes("Custom objects hold 2,000 of them (24%).") && text.includes("1 object is empty."), text);
check("text: one line per object, failures say why", text.includes("\nTask: 4,000") && text.includes("\nLead: 0")
  && text.includes("Ship__c: not counted (sObject type 'Ship__c' is not supported.)"), text);
check("text: singular for one object", recordCountsText("o", summarizeCounts([{ name: "A", count: 3, error: "" }])).includes("3 records across 1 object."));

console.log("\nfailures:", fails);
process.exit(fails ? 1 : 0);
