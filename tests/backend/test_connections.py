import os, sys, json, shutil, tempfile
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp                       # isolate Avio config / secrets from the real ones
for k in ("OPENCODE_API_KEY", "OPENCODE_BASE_URL", "OPENCODE_MODEL", "AVIO_SECRET_BACKEND", "AVIO_API_TOKEN", "ANTHROPIC_API_KEY"):
    os.environ.pop(k, None)
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
import ai_client, secret_store, connections
from ai_client import AIClient, Resolved

fails = 0
def check(name, cond, detail=""):
    global fails
    fails += (not cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail and not cond else ""))

class MemKeyring(KeyringBackend):
    priority = 5
    def __init__(self): self.d = {}
    def set_password(self, s, u, p): self.d[(s, u)] = p
    def get_password(self, s, u): return self.d.get((s, u))
    def delete_password(self, s, u):
        if (s, u) not in self.d: raise PasswordDeleteError("not stored")
        del self.d[(s, u)]

class ExplodingKeyring(MemKeyring):
    def set_password(self, s, u, p): raise OSError("The stub received bad data.")       # e.g. Windows size limit

class AmnesiacKeyring(MemKeyring):
    def set_password(self, s, u, p): pass                                              # silently stores nothing

mem = MemKeyring()
keyring.set_keyring(mem)
data_dir = ai_client.CONFIG_PATH.parent
def reset(kr=None):
    global mem
    mem = kr or MemKeyring()
    keyring.set_keyring(mem)
    os.environ.pop("AVIO_SECRET_BACKEND", None)
    for p in (ai_client.CONFIG_PATH, ai_client.API_KEY_PATH):
        p.unlink(missing_ok=True)
    shutil.rmtree(data_dir / "secrets", ignore_errors=True)
def raw_config_text(): return ai_client.CONFIG_PATH.read_text() if ai_client.CONFIG_PATH.exists() else ""
KEY = "sk-proj-" + "A1b2C3d4" * 19      # 160 chars, fake
KEY2 = "sk-ant-" + "Z9y8X7w6" * 12

# ================= secret_store =================
reset()
check("store: keystore is used and reported secure", secret_store.status() == {"kind": "keystore", "label": secret_store.status()["label"], "secure": True})
check("store: set returns 'keystore'; get round-trips", secret_store.set("a", KEY) == "keystore" and secret_store.get("a") == KEY)
secret_store.get("never-stored"); secret_store.delete("never-stored")
check("store: no plaintext file left behind, and reads/deletes don't even create the secrets folder", not (data_dir / "secrets").exists())
secret_store.delete("a")
check("store: delete removes it", secret_store.get("a") is None)
secret_store.delete("never-existed")
check("store: deleting a missing entry is harmless", True)

reset()
os.environ["AVIO_SECRET_BACKEND"] = "file"
check("store: forced file backend reports insecure", secret_store.status()["kind"] == "file" and secret_store.status()["secure"] is False)
check("store: file fallback set returns 'file'", secret_store.set("conn/1", KEY) == "file")
files = list((data_dir / "secrets").glob("*.key"))
check("store: file written under secrets/ with a sanitised name", len(files) == 1 and "/" not in files[0].name, str(files))
check("store: file fallback round-trips and deletes", secret_store.get("conn/1") == KEY and (secret_store.delete("conn/1") or True) and secret_store.get("conn/1") is None)

reset(ExplodingKeyring())
check("store: a keystore that raises falls back to the file", secret_store.set("x", KEY) == "file" and secret_store.get("x") == KEY)
reset(AmnesiacKeyring())
check("store: a keystore that silently drops data falls back to the file", secret_store.set("x", KEY) == "file" and secret_store.get("x") == KEY)

from keyring.backends import fail
reset(fail.Keyring())
check("store: the 'fail' backend counts as no keystore", secret_store.status()["kind"] == "file")
reset()
secret_store._file_set("late", KEY)
check("store: a value saved while no keystore existed is still readable later", secret_store.get("late") == KEY)
secret_store.set("late", KEY2)
check("store: writing to the keystore removes the stale plaintext copy", secret_store.get("late") == KEY2 and secret_store._file_get("late") is None)

# ================= connections =================
reset()
c1 = connections.upsert(label="OpenAI", preset="openai", base_url="https://api.openai.com/v1", model="gpt-5-mini", api_key=KEY)
check("conn: created with a slug id and made default", c1["id"] == "openai" and connections.default_id() == "openai")
check("conn: key is in the keystore, NOT in config.json", mem.get_password("Avio", "connection-openai") == KEY and KEY not in raw_config_text())
check("conn: public view has key_set and a masked hint, never the key", c1["key_set"] and c1["key_hint"] == "…" + KEY[-4:] and KEY not in json.dumps(connections.list_connections()))
c2 = connections.upsert(label="OpenAI", preset="openai", base_url="https://api.openai.com/v1/", model="gpt-4.1-mini", api_key=KEY2)
check("conn: duplicate label gets a unique id; default unchanged", c2["id"] == "openai-2" and connections.default_id() == "openai")
c3 = connections.upsert(label="Claude", preset="anthropic", base_url="https://api.anthropic.com/v1", model="claude-sonnet-4-6", api_key=KEY2, make_default=True)
check("conn: make_default switches the default", connections.default_id() == "claude")
u = connections.upsert(conn_id="claude", label="Claude work", preset="anthropic", base_url="https://api.anthropic.com/v1", model="claude-haiku-5-5")
check("conn: update with no api_key keeps the stored key", u["key_set"] and connections.key_for("claude") == KEY2 and u["model"] == "claude-haiku-5-5" and u["label"] == "Claude work")
connections.upsert(conn_id="claude", label="Claude work", preset="anthropic", base_url="https://api.anthropic.com/v1", model="x", api_key="   ")
check("conn: a blank api_key also keeps it", connections.key_for("claude") == KEY2)
connections.upsert(conn_id="claude", label="Claude work", preset="anthropic", base_url="https://api.anthropic.com/v1", model="x", api_key=KEY)
check("conn: a new api_key replaces it", connections.key_for("claude") == KEY)
u = connections.upsert(conn_id="claude", label="Claude work", preset="anthropic", base_url="https://api.anthropic.com/v1", model="x", clear_key=True)
check("conn: clear_key removes it", not u["key_set"] and connections.key_for("claude") is None and mem.get_password("Avio", "connection-claude") is None)
for bad in ("", "api.openai.com/v1", "ftp://x", "https://has space"):
    try: connections.upsert(label="x", base_url=bad); ok = False
    except ValueError: ok = True
    check(f"conn: invalid URL rejected: {bad!r}", ok)
try: connections.upsert(conn_id="nope", base_url="https://x/v1"); ok = False
except connections.UnknownConnection: ok = True
check("conn: updating an unknown id raises UnknownConnection", ok)
check("conn: local connections do not require a key", connections.upsert(label="Ollama", preset="ollama", base_url="http://localhost:11434/v1", model="llama3:8b")["requires_key"] is False)

reset()
connections.upsert(label="X", preset="openai", base_url="https://api.openai.com/v1", model="m", api_key=KEY)
connections.upsert(conn_id="x", label="X", preset="openai", base_url="https://api.openai.com/v1/", model="m2")
check("conn: a trailing-slash edit of the same host keeps the key", connections.key_for("x") == KEY)
u = connections.upsert(conn_id="x", label="X", preset="anthropic", base_url="https://api.anthropic.com/v1", model="claude-haiku-5-5")
check("conn: changing the host without a new key DROPS the old key (it is never sent to another provider)",
      connections.key_for("x") is None and not u["key_set"] and mem.get_password("Avio", "connection-x") is None)
connections.upsert(conn_id="x", label="X", preset="openai", base_url="https://api.openai.com/v1", model="m", api_key=KEY)
u = connections.upsert(conn_id="x", label="X", preset="anthropic", base_url="https://api.anthropic.com/v1", model="c", api_key=KEY2)
check("conn: changing the host WITH a new key stores the new key", connections.key_for("x") == KEY2 and u["key_set"])
reset()
connections.upsert(label="OpenAI", preset="openai", base_url="https://api.openai.com/v1", model="gpt-5-mini", api_key=KEY)
connections.upsert(label="OpenAI", preset="openai", base_url="https://api.openai.com/v1/", model="gpt-4.1-mini", api_key=KEY2)
connections.upsert(label="Claude", preset="anthropic", base_url="https://api.anthropic.com/v1", model="claude-sonnet-4-6", api_key=KEY2, make_default=True)
connections.upsert(conn_id="claude", label="Claude work", preset="anthropic", base_url="https://api.anthropic.com/v1", model="claude-haiku-5-5")
connections.upsert(label="Ollama", preset="ollama", base_url="http://localhost:11434/v1", model="llama3:8b")
connections.set_default("openai-2")
check("conn: set_default", connections.default_id() == "openai-2")
connections.delete("openai-2")
check("conn: deleting the default moves it to a remaining connection and removes the key",
      connections.default_id() in {"openai", "claude", "ollama"} and mem.get_password("Avio", "connection-openai-2") is None)
for cid in [c["id"] for c in connections.list_connections()]: connections.delete(cid)
check("conn: deleting all leaves no default", connections.default_id() is None and connections.list_connections() == [])
try: connections.delete("openai"); ok = False
except connections.UnknownConnection: ok = True
check("conn: deleting an unknown id raises", ok)

# ---- resolve ----
reset()
connections.upsert(label="OpenAI", preset="openai", base_url="https://api.openai.com/v1", model="gpt-5-mini", api_key=KEY)
connections.upsert(label="Claude", preset="anthropic", base_url="https://api.anthropic.com/v1", model="claude-haiku-5-5", api_key=KEY2)
r = connections.resolve("claude")
check("resolve: explicit id returns that connection's URL/model/key", (r.base_url, r.model, r.api_key, r.conn_id) == ("https://api.anthropic.com/v1", "claude-haiku-5-5", KEY2, "claude"))
r = connections.resolve(None)
check("resolve: no id uses the default connection", r.conn_id == "openai" and r.api_key == KEY and not r.local)
os.environ["OPENCODE_MODEL"] = "dev-model"
r = connections.resolve(None)
check("resolve: a model-only dev override applies on top of the default connection (its key and URL are kept)", r.model == "dev-model" and r.api_key == KEY and r.base_url == "https://api.openai.com/v1")
check("resolve: an explicit id ignores the dev override", connections.resolve("claude").model == "claude-haiku-5-5")
os.environ["OPENCODE_BASE_URL"] = "https://other-host.example.com/v1"
try: connections.resolve(None); msg = ""
except RuntimeError as e: msg = str(e)
check("resolve: an override that changes the HOST never borrows the connection's key", "No API key" in msg and KEY not in msg, msg)
os.environ["OPENCODE_API_KEY"] = "override-key"
r = connections.resolve(None)
check("resolve: ...but works when the override brings its own key", (r.base_url, r.api_key, r.model) == ("https://other-host.example.com/v1", "override-key", "dev-model"))
for k in ("OPENCODE_MODEL", "OPENCODE_BASE_URL", "OPENCODE_API_KEY"): os.environ.pop(k, None)
connections.upsert(conn_id="claude", label="Claude", preset="anthropic", base_url="https://api.anthropic.com/v1", model="claude-haiku-5-5", clear_key=True)
try: connections.resolve("claude"); msg = ""
except RuntimeError as e: msg = str(e)
check("resolve: missing key gives a readable 'No API key' message naming the connection", "No API key" in msg and "Claude" in msg, msg)
connections.upsert(label="NoModel", preset="custom", base_url="https://gw.example.com/v1", api_key=KEY)
try: connections.resolve("nomodel"); msg = ""
except RuntimeError as e: msg = str(e)
check("resolve: missing model gives a readable message", "No model" in msg and "NoModel" in msg, msg)
connections.upsert(label="Ollama", preset="ollama", base_url="http://localhost:11434/v1", model="llama3:8b")
r = connections.resolve("ollama")
check("resolve: a local connection works without a key and is flagged local", r.api_key == "" and r.local)
try: connections.resolve("ghost"); ok = False
except connections.UnknownConnection: ok = True
check("resolve: unknown id raises UnknownConnection", ok)
reset()
try: connections.resolve(None); msg = ""
except RuntimeError as e: msg = str(e)
check("resolve: nothing configured -> readable 'No API key' error", "No API key" in msg, msg)

# ---- migration ----
reset()
ai_client.API_KEY_PATH.write_text(KEY2)
ai_client.CONFIG_PATH.write_text(json.dumps({"model": "claude-sonnet-4-6", "base_url": "https://api.anthropic.com/v1", "theme": "dark"}))
cid = connections.migrate_legacy()
cfg = json.loads(raw_config_text())
check("migrate: key moved to the keystore under a new Default connection", cid and connections.key_for(cid) == KEY2 and connections.get_connection(cid)["preset"] == "anthropic")
check("migrate: model and URL carried over, preset detected", connections.get_connection(cid)["model"] == "claude-sonnet-4-6" and connections.get_connection(cid)["base_url"] == "https://api.anthropic.com/v1")
check("migrate: the plain-text key file is deleted", not ai_client.API_KEY_PATH.exists())
check("migrate: key not in config.json; legacy model/base_url removed; other settings kept", KEY2 not in raw_config_text() and "model" not in cfg and "base_url" not in cfg and cfg.get("theme") == "dark")
check("migrate: idempotent", connections.migrate_legacy() is None and len(connections.list_connections()) == 1)
reset()
check("migrate: nothing to do without a key file", connections.migrate_legacy() is None)
reset()
connections.upsert(label="Existing", preset="openai", base_url="https://api.openai.com/v1", model="m", api_key=KEY)
ai_client.API_KEY_PATH.write_text(KEY2)
check("migrate: leaves a stray key file alone when connections already exist", connections.migrate_legacy() is None and ai_client.API_KEY_PATH.exists())
reset()
ai_client.API_KEY_PATH.write_text("oc_sk_" + "q" * 40)
cid = connections.migrate_legacy()
c = connections.get_connection(cid)
check("migrate: an oc_sk_ key with no URL becomes the OpenCode gateway connection", c["preset"] == "opencode" and c["base_url"] == ai_client.OPENCODE_GATEWAY_URL, str(c))
reset()
ai_client.API_KEY_PATH.write_text(KEY)
real_get = secret_store.get
secret_store.get = lambda account: "something-else"          # keystore read-back does not match
cid = connections.migrate_legacy()
secret_store.get = real_get
check("migrate: if the read-back differs, the old key file is NOT deleted", ai_client.API_KEY_PATH.exists() and ai_client.API_KEY_PATH.read_text() == KEY)
reset()
ai_client.API_KEY_PATH.write_text(KEY)
os.environ["AVIO_SECRET_BACKEND"] = "file"
cid = connections.migrate_legacy()
check("migrate: with no keystore the key moves to the private file store and still works", cid and connections.key_for(cid) == KEY and not ai_client.API_KEY_PATH.exists())
os.environ.pop("AVIO_SECRET_BACKEND", None)
for key, preset, url in (("sk-ant-" + "q" * 40, "anthropic", "https://api.anthropic.com/v1"), ("sk-proj-" + "q" * 40, "openai", "https://api.openai.com/v1"),
                         ("AIza" + "q" * 35, "google", None), ("gsk_" + "q" * 40, "groq", None), ("weird-key-123456", "openai", "https://api.openai.com/v1")):
    reset()
    ai_client.API_KEY_PATH.write_text(key)
    cid = connections.migrate_legacy()
    c = connections.get_connection(cid) if cid else None
    check(f"migrate: a key with no saved URL is recognised by prefix ({key[:6]}… -> {preset})", c and c["preset"] == preset and (url is None or c["base_url"] == url) and c["base_url"].startswith("https://"), str(c))

# ---- AIClient: one SDK client per (URL, key) ----
ai = AIClient()
a = Resolved("https://api.openai.com/v1", "m", KEY); b = Resolved("https://api.anthropic.com/v1", "m", KEY2)
ca, cb = ai._client_for(a), ai._client_for(b)
check("client: different connections get different SDK clients, the same one is reused", ca is not cb and ai._client_for(a) is ca)
ai.invalidate()
check("client: invalidate() drops the cache", ai._client_for(a) is not ca)

# ================= HTTP endpoints =================
import main
from fastapi.testclient import TestClient
reset()

with TestClient(main.app) as tc:                       # context manager runs the startup migration
    r = tc.get("/api/ai/connections")
    check("api: empty list shape", r.status_code == 200 and r.json()["connections"] == [] and r.json()["storage"]["kind"] == "keystore" and len(r.json()["presets"]) > 3)

    r = tc.post("/api/ai/connections", json={"label": "OpenAI", "preset": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-5-mini", "api_key": KEY})
    body = r.text
    check("api: create returns the connection without the key", r.status_code == 200 and r.json()["connection"]["key_set"] and KEY not in body, body[:200])
    r = tc.post("/api/ai/connections", json={"label": "Bad", "base_url": "nope"})
    check("api: invalid URL -> 400 with a message", r.status_code == 400 and "http" in r.json()["detail"])
    r = tc.post("/api/ai/connections", json={"id": "ghost", "base_url": "https://x/v1"})
    check("api: updating a missing connection -> 404", r.status_code == 404)
    tc.post("/api/ai/connections", json={"label": "Claude", "preset": "anthropic", "base_url": "https://api.anthropic.com/v1", "model": "claude-haiku-5-5", "api_key": KEY2})

    texts = [tc.get("/api/ai/connections").text, tc.get("/api/settings").text,
             tc.post("/api/models", json={"connection": "claude"}).text, tc.post("/api/ai/connections/default", json={"id": "claude"}).text]
    check("api: no endpoint ever returns a key (list, settings, models, default)", all(KEY not in t and KEY2 not in t for t in texts))
    s = tc.get("/api/settings").json()
    check("api: /api/settings carries connections, default, storage and derives model/key_set from the default",
          s["default_connection"] == "claude" and len(s["connections"]) == 2 and s["model"] == "claude-haiku-5-5" and s["key_set"] and s["secret_storage"]["secure"] and s["key_source"] == "keystore")
    check("api: default endpoint 404 for unknown", tc.post("/api/ai/connections/default", json={"id": "ghost"}).status_code == 404)

    # Legacy "custom_skills" key: never used (skills are added in Settings -> Skills), now ignored everywhere.
    import sf_skills
    legacy_dir = data_dir / "legacy-custom-skill"
    legacy_dir.mkdir(exist_ok=True)
    (legacy_dir / "SKILL.md").write_text("LEGACY-CUSTOM-SKILL-MARKER", encoding="utf-8")
    cfg = json.loads(raw_config_text())
    cfg["custom_skills"] = [{"name": "Legacy", "path": str(legacy_dir)}]
    ai_client.CONFIG_PATH.write_text(json.dumps(cfg))
    r = tc.post("/api/settings", json={"theme": "dark", "custom_skills": [{"name": "X", "path": "C:/x"}]})
    check("api: an old client posting custom_skills still saves (key ignored)", r.status_code == 200 and json.loads(raw_config_text())["theme"] == "dark", r.text[:200])
    check("api: posted custom_skills is not written", json.loads(raw_config_text())["custom_skills"] == [{"name": "Legacy", "path": str(legacy_dir)}])
    check("api: /api/settings no longer returns custom_skills", "custom_skills" not in tc.get("/api/settings").json())
    check("skills config: custom_skills is not read", "custom_skills" not in sf_skills._load_skills_config())
    ctx, used = sf_skills.augment_with_skills("SYS", [{"role": "user", "content": "write a test class"}], None)
    check("skills: a legacy custom_skills folder is never injected", "LEGACY-CUSTOM-SKILL-MARKER" not in ctx and "Legacy" not in " ".join(used), str(used))
    check("skills: the dead loader is gone", not hasattr(sf_skills, "_load_custom_skill_context"))

    # models: uses the connection's stored key and URL, a typed key wins
    seen = {}
    real_fm = main.fetch_models
    main.fetch_models = lambda key, url: (seen.update(key=key, url=url) or ["m1", "m2"])
    r = tc.post("/api/models", json={"connection": "openai"})
    check("api: /api/models with a connection uses its stored URL and key", seen == {"key": KEY, "url": "https://api.openai.com/v1"} and r.json()["source"] == "live", str(seen))
    tc.post("/api/models", json={"connection": "openai", "api_key": "typed-key"})
    check("api: a typed key beats the stored one (re-test before saving)", seen["key"] == "typed-key")
    tc.post("/api/models", json={"connection": "openai", "base_url": "https://api.anthropic.com/v1"})
    check("api: the stored key is NOT sent to a different host typed in while editing", seen["url"] == "https://api.anthropic.com/v1" and seen["key"] is None, str(seen))
    tc.post("/api/models", json={"connection": "openai", "base_url": "https://api.openai.com/v1/"})
    check("api: ...but a trailing-slash variant of the same host still uses it", seen["key"] == KEY, str(seen))
    tc.post("/api/models", json={})
    check("api: a plain refresh uses the default connection", seen["url"] == "https://api.anthropic.com/v1" and seen["key"] == KEY2)
    r = tc.post("/api/models", json={"connection": "ghost"})
    check("api: /api/models for a missing connection falls back with an error, not a crash", r.json()["source"] == "fallback" and "no longer exists" in r.json()["error"])
    main.fetch_models = real_fm

    # fallback model list is narrowed to the provider (it used to offer Claude ids for OpenAI)
    def _boom(key, url): raise RuntimeError("401 invalid key")
    main.fetch_models = _boom
    def fb(url): return tc.post("/api/models", json={"base_url": url}).json()
    r = fb("https://api.openai.com/v1"); ids = [m["id"] for m in r["models"]]
    check("api: OpenAI fallback list has only OpenAI models (no Claude)", r["source"] == "fallback" and ids and all(i.startswith(("gpt-", "o")) for i in ids), str(ids))
    r = fb("https://api.anthropic.com/v1"); ids = [m["id"] for m in r["models"]]
    check("api: Anthropic fallback list has only Claude models", ids and all(i.startswith("claude-") for i in ids), str(ids))
    check("api: a local server's fallback list is empty (it is whatever you pulled)", fb("http://localhost:11434/v1")["models"] == [])
    check("api: an unknown gateway keeps the full built-in list", len(fb("https://gw.example.com/v1")["models"]) == len(main.AVAILABLE_MODELS))
    check("api: the fetch error is still reported", "401" in fb("https://api.openai.com/v1")["error"])
    main.fetch_models = real_fm

    # chat: connection selection and SSE errors
    captured = {}
    def fake_stream(messages, system=None, model=None, resolved=None, request_id=None):
        captured["resolved"] = resolved; captured["model"] = model; captured["system_len"] = len(system or "")
        yield "hi"; yield ai_client.StreamFinish("stop")
    main._ai.stream = fake_stream
    r = tc.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "x"}], "connection": "openai", "system": "S"})
    rs = captured["resolved"]
    check("api: chat uses the chosen connection (URL, model, key) and streams", rs.conn_id == "openai" and rs.model == "gpt-5-mini" and rs.api_key == KEY and rs.base_url == "https://api.openai.com/v1" and '"delta": "hi"' in r.text)
    r = tc.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "x"}]})
    check("api: chat with no connection uses the default", captured["resolved"].conn_id == "claude")
    r = tc.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "x"}], "model": "override-model", "connection": "openai"})
    check("api: an explicit model in the request still overrides the connection's", captured["model"] == "override-model")
    r = tc.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "x"}], "connection": "ghost"})
    check("api: chat with a deleted connection returns a readable SSE error", '"error"' in r.text and "no longer exists" in r.text and r.status_code == 200)
    tc.post("/api/ai/connections", json={"id": "openai", "label": "OpenAI", "preset": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-5-mini", "clear_key": True})
    r = tc.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "x"}], "connection": "openai"})
    check("api: chat with no saved key returns the 'No API key' SSE error", "No API key" in r.text and "OpenAI" in r.text, r.text[:200])
    tc.post("/api/ai/connections", json={"label": "Ollama", "preset": "ollama", "base_url": "http://localhost:11434/v1", "model": "llama3:8b"})
    aug = {}
    real_aug = main.augment_with_skills
    main.augment_with_skills = lambda system, messages, force=None, local=False: (aug.update(local=local) or (system or ""), [])
    tc.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "x"}], "connection": "ollama"})
    check("api: a local connection triggers the condensed-skills mode", aug.get("local") is True and captured["resolved"].local)
    tc.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "x"}], "connection": "claude"})
    check("api: a cloud connection does not", aug.get("local") is False)
    main.augment_with_skills = real_aug

    # delete
    r = tc.post("/api/ai/connections/delete", json={"id": "ollama"})
    check("api: delete connection", r.status_code == 200 and connections.get_connection("ollama") is None)
    check("api: delete a missing connection -> 404", tc.post("/api/ai/connections/delete", json={"id": "ollama"}).status_code == 404)

# legacy single-key POST /api/settings
reset()
with TestClient(main.app) as tc:
    r = tc.post("/api/settings", json={"api_key": KEY, "model": "gpt-5-mini", "base_url": "https://api.openai.com/v1", "theme": "dark"})
    cs = connections.list_connections()
    check("api: the old single-key form creates a Default connection and writes NO plain-text key file",
          r.status_code == 200 and len(cs) == 1 and cs[0]["key_set"] and cs[0]["model"] == "gpt-5-mini" and not ai_client.API_KEY_PATH.exists() and KEY not in raw_config_text())
    check("api: theme saved through the same call", json.loads(raw_config_text()).get("theme") == "dark")
    tc.post("/api/settings", json={"theme": "light"})
    check("api: a theme-only save leaves connections and their keys alone", len(connections.list_connections()) == 1 and connections.key_for(cs[0]["id"]) == KEY and connections.get_connection(cs[0]["id"])["model"] == "gpt-5-mini")

# startup migration through the app lifespan
reset()
ai_client.API_KEY_PATH.write_text(KEY2)
ai_client.CONFIG_PATH.write_text(json.dumps({"model": "claude-sonnet-4-6", "base_url": "https://api.anthropic.com/v1"}))
with TestClient(main.app) as tc:
    check("startup: the app migrates the old key file when it starts serving", len(connections.list_connections()) == 1 and not ai_client.API_KEY_PATH.exists() and connections.key_for(connections.default_id()) == KEY2)
    s = tc.get("/api/settings").json()
    check("startup: Settings shows the migrated connection as ready", s["key_set"] and s["model"] == "claude-sonnet-4-6" and s["connections"][0]["preset"] == "anthropic")

# ================= per-launch token =================
reset()
main._API_TOKEN = "T0KEN-abc"
with TestClient(main.app) as tc:
    check("token: a call without it -> 401", tc.get("/api/ai/connections").status_code == 401)
    check("token: a wrong token -> 401", tc.get("/api/ai/connections", headers={"Authorization": "Bearer nope"}).status_code == 401)
    check("token: the wrong scheme -> 401", tc.get("/api/ai/connections", headers={"Authorization": "T0KEN-abc"}).status_code == 401)
    check("token: the right token -> 200", tc.get("/api/ai/connections", headers={"Authorization": "Bearer T0KEN-abc"}).status_code == 200)
    check("token: /api/health stays open (polled before the token is known)", tc.get("/api/health").status_code == 200)
    check("token: API docs stay open (schema only)", tc.get("/docs").status_code == 200 and tc.get("/openapi.json").status_code == 200)
    check("token: POST endpoints are protected too", tc.post("/api/ai/connections", json={"label": "x", "base_url": "https://x/v1"}).status_code == 401 and connections.list_connections() == [])
    check("token: shutdown is protected", tc.post("/api/shutdown").status_code == 401)
    pre = tc.options("/api/ai/connections", headers={"Origin": "http://tauri.localhost", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
    check("token: CORS preflight (no credentials) is allowed and permits the Authorization header", pre.status_code == 200 and "authorization" in pre.headers.get("access-control-allow-headers", "").lower())
    main._ai.stream = lambda messages, system=None, model=None, resolved=None, request_id=None: iter(["ok", ai_client.StreamFinish("stop")])
    connections.upsert(label="X", preset="custom", base_url="https://gw/v1", model="m", api_key=KEY)
    body = {"messages": [{"role": "user", "content": "x"}]}
    check("token: the SSE chat stream is protected", tc.post("/api/claude/chat", json=body).status_code == 401)
    r = tc.post("/api/claude/chat", json=body, headers={"Authorization": "Bearer T0KEN-abc"})
    check("token: the SSE chat stream works with the token", r.status_code == 200 and '"delta": "ok"' in r.text)
main._API_TOKEN = ""
with TestClient(main.app) as tc:
    check("token: unset (dev mode) means open, as before", tc.get("/api/ai/connections").status_code == 200)

# ================= OpenRouter regions =================
G, EU, US = "https://openrouter.ai/api/v1", "https://eu.openrouter.ai/api/v1", "https://us.openrouter.ai/api/v1"
orp = next(p for p in ai_client.PROVIDER_PRESETS if p["id"] == "openrouter")
check("regions: the OpenRouter preset offers Global, EU and US with their addresses",
      [(r["id"], r["base_url"]) for r in orp["regions"]] == [("global", G), ("eu", EU), ("us", US)] and orp["base_url"] == G)
check("regions: no other preset has regions", all("regions" not in p for p in ai_client.PROVIDER_PRESETS if p["id"] != "openrouter"))
same = ai_client.same_key_scope
check("scope: the three OpenRouter addresses share one key", same(G, US) and same(US, EU) and same(EU, G) and same(US + "/", US))
check("scope: OpenRouter vs another provider is a different key scope", not same(G, "https://api.openai.com/v1") and not same("https://api.openai.com/v1", US))
check("scope: lookalike hosts are not trusted", not same(G, "https://us.openrouter.ai.evil.example/api/v1") and not same(G, "https://openrouter.ai.evil.example/api/v1") and not same(G, "http://us.openrouter.ai/api/v1"))
check("scope: same URL, and providers without regions, behave as before", same("https://api.openai.com/v1", "https://api.openai.com/v1/") and not same("https://api.openai.com/v1", "https://api.anthropic.com/v1"))
check("scope: blank URLs do not match a region", not same("", US) and same("", ""))
check("preset detection: every region address is OpenRouter", all(connections._preset_for(u, "") == "openrouter" for u in (G, EU, US, US + "/")))

reset()
connections.upsert(label="OR", preset="openrouter", base_url=G, model="google/gemma-4-31b-it", api_key=KEY)
u = connections.upsert(conn_id="or", label="OR", preset="openrouter", base_url=US, model="google/gemma-4-31b-it")
check("region switch: Global -> US keeps the saved key", u["key_set"] and connections.key_for("or") == KEY and u["base_url"] == US)
u = connections.upsert(conn_id="or", label="OR", preset="openrouter", base_url=EU, model="google/gemma-4-31b-it")
check("region switch: US -> EU keeps it too", connections.key_for("or") == KEY and u["base_url"] == EU)
check("region switch: the key resolves for the new region address", connections.resolve("or").api_key == KEY and connections.resolve("or").base_url == EU)
u = connections.upsert(conn_id="or", label="OR", preset="openai", base_url="https://api.openai.com/v1", model="gpt-5")
check("region switch: leaving OpenRouter for another provider still DROPS the key", connections.key_for("or") is None and not u["key_set"])
reset()
connections.upsert(label="OR", preset="openrouter", base_url=US, model="m", api_key=KEY)
connections.upsert(conn_id="or", label="OR", preset="custom", base_url="https://us.openrouter.ai.evil.example/api/v1", model="m")
check("region switch: a lookalike host drops the key", connections.key_for("or") is None)

with TestClient(main.app) as tc:
    reset()
    r = tc.get("/api/ai/connections")
    orx = next(p for p in r.json()["presets"] if p["id"] == "openrouter")
    check("api: presets expose the OpenRouter regions to the UI", [x["id"] for x in orx["regions"]] == ["global", "eu", "us"])
    check("api: /api/settings providers expose them too", next(p for p in tc.get("/api/settings").json()["providers"] if p["id"] == "openrouter").get("regions"))
    tc.post("/api/ai/connections", json={"label": "OR", "preset": "openrouter", "base_url": G, "model": "m", "api_key": KEY})
    seen = {}
    real_fm = main.fetch_models
    main.fetch_models = lambda key, url: (seen.update(key=key, url=url) or ["a/b"])
    tc.post("/api/models", json={"connection": "or", "base_url": US})
    check("api: model list for another OpenRouter region uses the saved key", seen == {"key": KEY, "url": US}, str(seen))
    tc.post("/api/models", json={"connection": "or", "base_url": "https://api.openai.com/v1"})
    check("api: ...but a different provider still does not", seen["key"] is None, str(seen))
    main.fetch_models = real_fm

shutil.rmtree(tmp, ignore_errors=True)
print("\nfailures:", fails)
sys.exit(1 if fails else 0)
