import sys, os, tempfile, json
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp; os.environ["HOME"] = tmp; os.environ["XDG_DATA_HOME"] = tmp
os.environ.pop("AVIO_API_TOKEN", None)
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import main
from fastapi.testclient import TestClient

# /api/soql's totalSize, which Record Counts (SOQL Runner and AI Chat) reads. The sf CLI call is replaced by
# canned `sf data query --json` results, so this runs offline on every platform.
fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

calls = []
REPLY = {}
def fake_sf_raw(*args):
    calls.append(list(args))
    r = REPLY["value"]
    if isinstance(r, Exception): raise r
    return r
main._sf_raw = fake_sf_raw
tc = TestClient(main.app)
def soql(query, reply, alias="org-one"):
    REPLY["value"] = reply
    return tc.post("/api/soql", json={"alias": alias, "query": query})

r = soql("SELECT COUNT() FROM Account", {"status": 0, "result": {"done": True, "totalSize": 48213, "records": []}})
check("COUNT(): 200", r.status_code == 200, r.text)
check("COUNT(): totalSize is the org's number, not len(records)", r.json() == {"records": [], "totalSize": 48213}, r.text)
check("the CLI got data query --query <soql> --target-org <alias>",
      calls[-1] == ["data", "query", "--query", "SELECT COUNT() FROM Account", "--target-org", "org-one"], str(calls[-1]))

r = soql("SELECT COUNT() FROM Empty__c", {"status": 0, "result": {"done": True, "totalSize": 0, "records": []}})
check("COUNT() of an empty object: 0", r.json()["totalSize"] == 0, r.text)

recs = [{"attributes": {"type": "Account", "url": "/x/1"}, "Id": "001A", "Name": "One"},
        {"attributes": {"type": "Account", "url": "/x/2"}, "Id": "001B", "Name": "Two"}]
r = soql("SELECT Id, Name FROM Account LIMIT 2", {"status": 0, "result": {"done": True, "totalSize": 2, "records": recs}})
check("normal query: attributes stripped, records kept", r.json()["records"] == [{"Id": "001A", "Name": "One"}, {"Id": "001B", "Name": "Two"}], r.text)
check("normal query: totalSize 2", r.json()["totalSize"] == 2, r.text)

r = soql("SELECT Id FROM Account LIMIT 2", {"status": 0, "result": {"done": False, "totalSize": 9000, "records": recs}})
check("a partial result keeps the org's totalSize (more than came back)", r.json()["totalSize"] == 9000, r.text)

r = soql("SELECT Id FROM Account", {"status": 0, "result": {"records": recs}})
check("totalSize missing: falls back to len(records)", r.json()["totalSize"] == 2, r.text)
for junk in ("12", None, 3.5, [1]):
    r = soql("SELECT Id FROM Account", {"status": 0, "result": {"totalSize": junk, "records": recs}})
    check(f"totalSize {junk!r} (not an int): falls back to len(records)", r.json()["totalSize"] == 2, r.text)

r = soql("SELECT COUNT() FROM Nope__c", RuntimeError("sObject type 'Nope__c' is not supported."))
check("a CLI error is a 500 carrying the message (the Counts note shows it)", r.status_code == 500 and "Nope__c" in r.text, r.text)

print("\nfailures:", fails)
sys.exit(1 if fails else 0)
