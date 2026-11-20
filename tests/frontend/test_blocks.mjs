import { pathToFileURL, fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../../frontend/src/", import.meta.url));
const { parseBlocks, isLang, APEX_LANGS, SOQL_LANGS } = await import(pathToFileURL(root + "aiBlocks.js").href);
const { buildExportFiles } = await import(pathToFileURL(root + "apexExport.js").href);

let fails = 0;
const check = (name, ok, detail = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? "  -- " + detail : "")); };
const code = (t) => parseBlocks(t).filter((p) => p.type === "code");

let b = code("a\n```apex\npublic class A {}\n```\nb");
check("apex block: lang captured, content clean", b.length === 1 && b[0].lang === "apex" && b[0].content === "public class A {}", JSON.stringify(b));

b = code("```xml\n<ApexClass/>\n```");
check("xml block: lang is xml and 'xml' is NOT in the content (old bug)", b[0].lang === "xml" && b[0].content === "<ApexClass/>", JSON.stringify(b));

b = code("```\nplain\n```");
check("no language: lang empty, content intact", b[0].lang === "" && b[0].content === "plain");

b = code("```SELECT Id FROM Account```");
check("one-line fence is not mistaken for a language", b.length === 1 && b[0].lang === "" && b[0].content === "SELECT Id FROM Account", JSON.stringify(b));

b = code("```apex\r\npublic class A {}\r\n```");
check("CRLF after the language tag", b[0].lang === "apex" && b[0].content.startsWith("public class A"));

b = code("```Apex\nclass X {}\n```");
check("language is lower-cased", b[0].lang === "apex");

const cut = "Intro\n```apex\npublic class Test {\n  void a() {";
const pc = parseBlocks(cut);
check("unclosed (cut-off) fence stays plain text, not a code block", pc.every((p) => p.type === "text") && pc.map((p) => p.content).join("") === cut);

const text = "I'll build both.\n\n### TestDataFactory.cls\n```apex\n@IsTest\npublic with sharing class TestDataFactory {\n  public static Account make() { return new Account(Name='x'); }\n}\n```\n\n### meta\n```xml\n<?xml version=\"1.0\"?>\n<ApexClass><apiVersion>66.0</apiVersion></ApexClass>\n```\n\n### AccountCreationTest.cls\n```apex\n@IsTest\nprivate class AccountCreationTest {\n  @IsTest static void t() { System.assert(true); }\n}\n```\nDone.";
const blocks = code(text);
check("Claude-style answer: 3 code blocks, langs apex/xml/apex", blocks.map((x) => x.lang).join() === "apex,xml,apex");
const apexOnly = blocks.filter((x) => isLang(x.lang, APEX_LANGS)).map((x) => x.content);
const files = buildExportFiles(apexOnly, "68.0").map((f) => f.fileName);
check("Avio export of the apex-only blocks finds both classes", files.length === 2 && files.includes("TestDataFactory.cls") && files.includes("AccountCreationTest.cls"), JSON.stringify(files));
check("the xml block is not insertable into the Apex editor", !isLang("xml", APEX_LANGS) && !isLang("json", APEX_LANGS) && !isLang("bash", APEX_LANGS));
check("apex/java/blank are insertable", isLang("apex", APEX_LANGS) && isLang("java", APEX_LANGS) && isLang("", APEX_LANGS) && isLang(undefined, APEX_LANGS));
check("soql/sql/blank are insertable into the SOQL editor", isLang("soql", SOQL_LANGS) && isLang("sql", SOQL_LANGS) && isLang("", SOQL_LANGS) && !isLang("xml", SOQL_LANGS));

const mixed = parseBlocks("t1 ```apex\nA\n``` t2 ```soql\nB\n``` t3");
check("text/code ordering preserved", mixed.map((p) => p.type).join() === "text,code,text,code,text", mixed.map((p) => p.type).join());

console.log("\nfailures:", fails);
process.exit(fails ? 1 : 0);
