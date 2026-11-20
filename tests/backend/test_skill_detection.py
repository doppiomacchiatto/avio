"""detect_skills(): which built-in skill (Apex / SOQL) an AI Chat prompt gets without forcing one.
Positive and negative phrase tables; only user messages (the last 6) are matched."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import sf_skills
from sf_skills import detect_skills, APEX_SKILL as A, SOQL_SKILL as S

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

def got(text):
    return set(detect_skills([{"role": "user", "content": text}]))

APEX_YES = [
    "write a trigger on Account that sets the rating",
    "write a test class for my AccountService",
    "add @isTest to this",
    "how do I write batch apex for 2M records",
    "make it implement Database.Batchable",
    "convert this to a batchable job",
    "should this be queueable or a future method?",
    "a schedulable that runs nightly",
    "use @future(callout=true)",
    "expose it as an invocable method for Flow",
    "add @InvocableMethod",
    "add @AuraEnabled(cacheable=true)",
    "write a selector class for Opportunity",
    "split it into a service class and a domain class",
    "how to avoid governor limits here",
    "move the DML out of the loop",
    "too many DML statements: 151",
    "public with sharing class InvoiceController {",
    "global without sharing class Foo",
    "class MyBatch implements Database.Batchable<SObject>",
    "public class Foo implements Queueable",
    "System.enqueueJob(new Foo());",
    "wrap it in Test.startTest() and Test.stopTest()",
    "System.assertEquals fails",
    "it runs in before insert",
    "handle after update only",
    "write a trigger handler",
    "explain bulkification",
    "Database.insert(records, false)",
    "how do I raise code coverage",
    "write unit tests for it",
    "MyController.cls throws an error",
]
APEX_NO = [
    "what's the weather like",
    "summarize this email for me",
    "help me write a polite reply",
    "how do I export a report to Excel",
    "explain what a permission set is",
    "the batch of cookies is ready",
    "this class of problems is hard",
    "what are the service hours",
    "he showed great domain knowledge",
    "please assert your position in the meeting",
    "what happens after the update to Windows",
]
SOQL_YES = [
    "write a SOQL query",
    "is SOSL better here?",
    "SELECT Id, Name FROM Account WHERE Industry = 'Tech'",
    "select id from contact limit 5",
    "select Name, (select LastName from Contacts) from Account",
    "SELECT COUNT() FROM Lead",
    "select Amount from Opportunity",
    "select Custom_Field__c from Invoice__c",
    "query all accounts created this week",
    "query the opportunities closing this month",
    "how do I query contacts by email",
    "get the records with a query",
    "a query on Invoice__c by status",
    "look up the contacts for this account",
    "count opportunities by stage with GROUP BY",
    "sum Amount using an aggregate query",
    "AggregateResult[] groups = ...",
    "write a relationship query from Contact to Account",
    "use a subquery for the child cases",
    "is this a selective query?",
    "check the query plan",
    "FROM Account WHERE",
    "[SELECT Id FROM Case]",
    "Database.query(q)",
    "Database.getQueryLocator",
    "what's in the where clause",
]
SOQL_NO = [
    "what's the weather like",
    "I have a query about my invoice",
    "any queries, let me know",
    "select the best option from the list",
    "please select one",
    "order by date in Excel",
    "add an index to the book",
    "the aggregate score was high",
    "pick one from the menu",
    "limit 5 per person",
]

for t in APEX_YES:
    check(f"apex yes: {t!r}", A in got(t), str(got(t)))
for t in APEX_NO:
    check(f"apex no: {t!r}", A not in got(t), str(got(t)))
for t in SOQL_YES:
    check(f"soql yes: {t!r}", S in got(t), str(got(t)))
for t in SOQL_NO:
    check(f"soql no: {t!r}", S not in got(t), str(got(t)))

# accepted false positive, documented in sf_skills: a bare "trigger" is an Apex keyword
check("accepted: 'trigger a deploy' adds Apex", A in got("trigger a deploy"))
check("both: 'write a soql query in apex'", got("write a soql query in apex") == {A, S})

# only user messages, only the last 6
msgs = [{"role": "assistant", "content": "SELECT Id FROM Account; public with sharing class X"},
        {"role": "user", "content": "thanks"}]
check("assistant text is ignored", detect_skills(msgs) == [])
old = [{"role": "user", "content": "write a test class"}] + [{"role": "user", "content": "hi"}] * 6
check("a user message older than the last 6 is ignored", detect_skills(old) == [])
check("within the last 6 it counts", detect_skills(old[1:][:5] + old[:1]) == [A])
check("non-string content is ignored", detect_skills([{"role": "user", "content": [{"type": "text"}]}]) == [])
check("force still adds a skill with no keyword", detect_skills([{"role": "user", "content": "hello"}], [A]) == [A])
check("order is SOQL then Apex", detect_skills([{"role": "user", "content": "soql in a trigger"}]) == [S, A])

print("\nfailures:", fails)
sys.exit(1 if fails else 0)
