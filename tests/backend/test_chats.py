import sys, os, tempfile, json, time
from pathlib import Path
from datetime import datetime, timedelta, timezone
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp; os.environ["HOME"] = tmp; os.environ["XDG_DATA_HOME"] = tmp
os.environ["AVIO_API_TOKEN"] = "test-token"
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import chat_store

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
U = lambda t: {"role": "user", "content": t}
A = lambda t, **k: {"role": "assistant", "content": t, **k}
D = chat_store.chats_dir()

# ---- clean_messages ---------------------------------------------------------------------------------
m = chat_store.clean_messages([
    U("hello"), A("hi", skills=["Apex Generate", 5, "", "x" * 300], extra="drop me"),
    {"role": "system", "content": "no"}, {"role": "user", "content": 5}, {"role": "user", "content": "   "},
    {"role": "assistant", "content": "notice", "system": True}, "junk", None, A(""),
    {"role": "user", "content": "<script>alert(1)</script>"},
])
check("keeps only valid user/assistant text", [x["role"] for x in m] == ["user", "assistant", "user"], str(m))
check("unknown fields dropped", set(m[1].keys()) == {"role", "content", "skills"}, str(m[1]))
check("skills filtered to non-empty strings, long names cut", m[1]["skills"] == ["Apex Generate", "x" * 100], str(m[1]))
check("HTML stays as plain text", m[2]["content"] == "<script>alert(1)</script>")
check("user messages never carry skills", "skills" not in chat_store.clean_messages([U("a") | {"skills": ["x"]}])[0])
check("non-list input gives empty", chat_store.clean_messages("x") == [] and chat_store.clean_messages(None) == [])

# ---- ids -----------------------------------------------------------------------------------------------
for good in ("apex-20261116-120000", "soql-20261116-120000-2", "chat-20261116-120000"):
    check(f"valid id {good}", chat_store.valid_id(good))
for bad in ("../x", "apex-20261116-120000/../../config", "apex-2026-1", "x-20261116-120000", "apex-20261116-120000.json",
            "apex-20261116-120000\n", "", None, 5, "APEX-20261116-120000", "apex-20261116-120000-"):
    check(f"invalid id {bad!r}", not chat_store.valid_id(bad))

# ---- save / list / get --------------------------------------------------------------------------------
s = chat_store.save_chat("apex", [U("Write a test class for Account"), A("Sure", skills=["Apex Test Generate"])], now=NOW)
check("save returns id/surface/count/title", s["id"] == "apex-20261116-120000" and s["surface"] == "apex" and s["count"] == 2
      and s["title"] == "Write a test class for Account" and s["dropped"] == 0, str(s))
check("file is where we expect", (D / "apex-20261116-120000.json").exists())
raw = json.loads((D / "apex-20261116-120000.json").read_text(encoding="utf-8"))
check("file has version, surface, saved_at and nothing about connections or keys",
      raw["avio_chat"] == 1 and raw["surface"] == "apex" and raw["saved_at"] == "2026-11-16T12:00:00Z"
      and not {"connection", "api_key", "base_url", "url"} & set(raw), str(list(raw)))
s2 = chat_store.save_chat("apex", [U("again")], now=NOW)
check("same-second save gets a -2 id, nothing overwritten", s2["id"] == "apex-20261116-120000-2"
      and (D / "apex-20261116-120000.json").exists())
chat_store.save_chat("soql", [U("select")], now=NOW + timedelta(seconds=5))
chat_store.save_chat("chat", [U("q"), A("a")], now=NOW + timedelta(seconds=9))
l = chat_store.list_chats(now=NOW + timedelta(seconds=10))
check("list: newest first across surfaces", [x["surface"] for x in l] == ["chat", "soql", "apex", "apex"], str(l))
check("list: filter by surface", [x["id"] for x in chat_store.list_chats("apex", now=NOW + timedelta(seconds=10))] == ["apex-20261116-120000-2", "apex-20261116-120000"])
check("list carries no message bodies", all("messages" not in x for x in l))
check("list shows when a chat expires", l[-1]["expires_at"] == "2026-11-19T12:00:00Z", str(l[-1]))
g = chat_store.get_chat("apex-20261116-120000", now=NOW + timedelta(seconds=10))
check("get returns the messages with skills", g["messages"][1]["skills"] == ["Apex Test Generate"] and g["count"] == 2, str(g))

try: chat_store.list_chats("evil"); check("unknown surface rejected on list", False, "no error")
except chat_store.InvalidChat: check("unknown surface rejected on list", True)
for surf in ("fls", "profiles", "rest"):   # the AI panels on FLS Explorer, Profiles & PermSets and REST Explorer
    tab = chat_store.save_chat(surf, [U("x")], now=NOW + timedelta(seconds=20))
    check(f"save accepts the {surf} tab", tab["surface"] == surf and chat_store.get_chat(tab["id"], now=NOW + timedelta(seconds=21))["count"] == 1, str(tab))
    chat_store.delete_chat(tab["id"])
for surf in ("evil", "", "../x", "APEX"):
    try: chat_store.save_chat(surf, [U("x")], now=NOW); check(f"save rejects surface {surf!r}", False, "no error")
    except chat_store.InvalidChat: check(f"save rejects surface {surf!r}", True)
for empty in ([], [{"role": "system", "content": "x"}], [A("   ")], "nope", None):
    try: chat_store.save_chat("apex", empty, now=NOW); check(f"nothing to save rejected {str(empty)[:30]!r}", False, "no error")
    except chat_store.InvalidChat: check(f"nothing to save rejected {str(empty)[:30]!r}", True)
for bad in ("../config", "apex-20261116-120000/../../x", "..\\x", "nope"):
    try: chat_store.get_chat(bad); check(f"get with bad id {bad!r} is unknown", False, "no error")
    except chat_store.UnknownChat: check(f"get with bad id {bad!r} is unknown", True)
    try: chat_store.delete_chat(bad); check(f"delete with bad id {bad!r} is unknown", False, "no error")
    except chat_store.UnknownChat: check(f"delete with bad id {bad!r} is unknown", True)
outside = D.parent / "secret.json"; outside.write_text("{}")   # D.parent is the Avio data dir on every platform
try: chat_store.delete_chat("../secret"); except_ok = False
except chat_store.UnknownChat: except_ok = True
check("a traversal delete cannot touch a file outside chats/", except_ok and outside.exists())

# ---- title ---------------------------------------------------------------------------------------------
t = chat_store.save_chat("chat", [U("word " * 40)], now=NOW + timedelta(seconds=20))["title"]
check("long titles are cut to 60 + ellipsis, whitespace collapsed", len(t) == 63 and t.endswith("...") and "  " not in t, repr(t))
check("explicit title wins", chat_store.save_chat("chat", [U("x")], title="  My   title ", now=NOW + timedelta(seconds=21))["title"] == "My title")

# ---- caps ---------------------------------------------------------------------------------------------
many = [U(f"m{i}") if i % 2 == 0 else A(f"m{i}") for i in range(700)]
r = chat_store.save_chat("soql", many, now=NOW + timedelta(seconds=30))
saved = chat_store.get_chat(r["id"], now=NOW + timedelta(seconds=31))
check("over 500 messages: oldest dropped, newest kept", r["dropped"] == 200 and saved["count"] == 500
      and saved["messages"][0]["content"] == "m200" and saved["messages"][-1]["content"] == "m699", str(r))
big = [U("a" * 900_000), A("b" * 900_000), U("c" * 900_000)]
r = chat_store.save_chat("soql", big, now=NOW + timedelta(seconds=32))
saved = chat_store.get_chat(r["id"], now=NOW + timedelta(seconds=33))
check("over 2M characters: oldest dropped to fit", r["dropped"] == 1 and saved["count"] == 2 and saved["messages"][0]["content"].startswith("b"), str(r))

# ---- atomic write -------------------------------------------------------------------------------------
check("no temp files left behind", not list(D.glob("*.tmp")))
orig = os.replace
def boom(*a, **k): raise OSError("disk full")
os.replace = boom
try:
    chat_store.save_chat("apex", [U("x")], now=NOW + timedelta(seconds=40)); check("failed write raises", False, "no error")
except OSError:
    check("failed write raises", True)
finally:
    os.replace = orig
check("failed write leaves no temp or partial file", not list(D.glob("*.tmp")) and not (D / "apex-20261116-120040.json").exists())

# ---- retention: 3 days ------------------------------------------------------------------------------------
for p in D.glob("*.json"): p.unlink()
old = chat_store.save_chat("apex", [U("old")], now=NOW)
mid = chat_store.save_chat("soql", [U("mid")], now=NOW + timedelta(days=1, hours=23))
check("a chat 2 days 23h old is kept", {x["id"] for x in chat_store.list_chats(now=NOW + timedelta(days=2, hours=23))} == {old["id"], mid["id"]})
check("RETENTION_DAYS is 3", chat_store.RETENTION_DAYS == 3)
l = chat_store.list_chats(now=NOW + timedelta(days=3, seconds=1))
check("older than 3 days is gone from the list", [x["id"] for x in l] == [mid["id"]], str(l))
check("and the file itself is deleted", not (D / f"{old['id']}.json").exists())
try: chat_store.get_chat(old["id"], now=NOW + timedelta(days=3, seconds=1)); check("expired get is unknown", False, "no error")
except chat_store.UnknownChat: check("expired get is unknown", True)
exact = chat_store.save_chat("chat", [U("edge")], now=NOW + timedelta(days=10))
check("exactly 3 days old is still kept", exact["id"] in {x["id"] for x in chat_store.list_chats(now=NOW + timedelta(days=13))})
check("one second past 3 days is gone", exact["id"] not in {x["id"] for x in chat_store.list_chats(now=NOW + timedelta(days=13, seconds=1))})

# saving also purges, corrupt/foreign files are cleaned
for p in D.glob("*.json"): p.unlink()
(D / "apex-20200101-000000.json").write_text("not json")
(D / "apex-20200101-000001.json").write_text(json.dumps({"avio_chat": 99, "saved_at": NOW.isoformat(), "messages": []}))
(D / "notes.json").write_text("{}")
(D / ".chat-leftover.tmp").write_text("x")
chat_store.save_chat("apex", [U("fresh")], now=NOW)
left = sorted(p.name for p in D.glob("*"))
check("corrupt, wrong-version, foreign-named and temp files are removed on save", left == ["apex-20261116-120000.json"], str(left))
(D / "chat-20261116-130000.json").write_text(json.dumps({"avio_chat": 1, "surface": "chat", "saved_at": "garbage", "messages": [U("x")]}))
check("bad saved_at, fresh mtime: kept", "chat-20261116-130000" in {x["id"] for x in chat_store.list_chats(now=datetime.now(timezone.utc))})

# file-count safety net
for p in D.glob("*.json"): p.unlink()
for i in range(65):
    chat_store.save_chat("chat", [U(f"c{i}")], now=NOW + timedelta(seconds=i))
n = len(list(D.glob("*.json")))
check("never more than 60 saved chats; oldest go first", n == 60 and not (D / "chat-20261116-120004.json").exists()
      and (D / "chat-20261116-120005.json").exists(), str(n))

# delete / delete_all
cid = chat_store.list_chats("chat", now=NOW + timedelta(seconds=70))[0]["id"]
chat_store.delete_chat(cid)
check("delete removes one", not (D / f"{cid}.json").exists())
try: chat_store.delete_chat(cid); check("deleting twice is unknown", False, "no error")
except chat_store.UnknownChat: check("deleting twice is unknown", True)
(D / "keep-me.txt").write_text("x")
check("delete_all reports the count", chat_store.delete_all() == 59)
check("delete_all leaves foreign files alone and empties the list", (D / "keep-me.txt").exists() and chat_store.list_chats(now=NOW + timedelta(seconds=70)) == [])

# ---- HTTP endpoints -----------------------------------------------------------------------------------------
import main
from fastapi.testclient import TestClient
H = {"Authorization": "Bearer test-token"}
for p in D.glob("*"): p.unlink()
with TestClient(main.app) as tc:
    check("auth: list without token -> 401", tc.get("/api/chats").status_code == 401)
    check("auth: save without token -> 401", tc.post("/api/chats", json={"surface": "apex", "messages": [U("x")]}).status_code == 401)
    check("auth: delete-all without token -> 401", tc.post("/api/chats/delete-all").status_code == 401)
    check("auth: wrong token -> 401", tc.get("/api/chats", headers={"Authorization": "Bearer nope"}).status_code == 401)
    r = tc.get("/api/chats", headers=H)
    check("empty list", r.status_code == 200 and r.json() == {"chats": [], "retention_days": 3}, r.text)
    r = tc.post("/api/chats", headers=H, json={"surface": "apex", "messages": [U("Explain this"), A("It does X", skills=["Apex Generate"])]})
    j = r.json()
    check("save over HTTP", r.status_code == 200 and j["surface"] == "apex" and j["count"] == 2 and j["id"].startswith("apex-"), r.text)
    cid = j["id"]
    r = tc.get(f"/api/chats/{cid}", headers=H)
    check("get over HTTP", r.status_code == 200 and r.json()["messages"][1]["skills"] == ["Apex Generate"], r.text)
    check("list filter over HTTP", len(tc.get("/api/chats?surface=apex", headers=H).json()["chats"]) == 1
          and tc.get("/api/chats?surface=soql", headers=H).json()["chats"] == [])
    check("unknown surface -> 400", tc.get("/api/chats?surface=evil", headers=H).status_code == 400)
    check("save bad surface -> 400", tc.post("/api/chats", headers=H, json={"surface": "evil", "messages": [U("x")]}).status_code == 400)
    check("save empty -> 400 with a clear message", "nothing to save" in tc.post("/api/chats", headers=H, json={"surface": "apex", "messages": []}).text)
    check("save malformed body -> 422", tc.post("/api/chats", headers=H, json={"surface": "apex", "messages": "x"}).status_code == 422)
    check("get unknown -> 404 mentioning the retention", tc.get("/api/chats/apex-20200101-000000", headers=H).status_code == 404)
    check("get traversal-looking id -> 404, never a file read", tc.get("/api/chats/..%2F..%2Fconfig", headers=H).status_code in (404, 422))
    check("get id with dots -> 404", tc.get("/api/chats/apex-20200101-000000.json", headers=H).status_code == 404)
    check("delete bad id -> 404", tc.post("/api/chats/delete", headers=H, json={"id": "../config"}).status_code == 404)
    r = tc.post("/api/chats/delete", headers=H, json={"id": cid})
    check("delete over HTTP (POST alias)", r.status_code == 200 and tc.get(f"/api/chats/{cid}", headers=H).status_code == 404)
    tc.post("/api/chats", headers=H, json={"surface": "chat", "messages": [U("a")]})
    tc.post("/api/chats", headers=H, json={"surface": "soql", "messages": [U("b")]})
    r = tc.post("/api/chats/delete-all", headers=H)
    check("delete-all over HTTP", r.status_code == 200 and r.json()["deleted"] == 2 and tc.get("/api/chats", headers=H).json()["chats"] == [], r.text)

# startup purges expired chats
old_file = D / "apex-20200101-000000.json"
old_file.write_text(json.dumps({"avio_chat": 1, "surface": "apex", "saved_at": "2020-01-01T00:00:00Z", "title": "t", "messages": [U("x")]}))
with TestClient(main.app) as tc:
    pass
check("startup deletes an expired chat", not old_file.exists())

# the stored file never contains anything the app did not send
tc2 = TestClient(main.app)
r = tc2.post("/api/chats", headers=H, json={"surface": "chat", "messages": [U("hi") | {"api_key": "sk-secret", "connection": "x"}]})
body = (D / f"{r.json()['id']}.json").read_text(encoding="utf-8")
check("extra fields in the request are not stored", "sk-secret" not in body and "connection" not in body, body)

print(f"\n{'ALL PASSED' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
