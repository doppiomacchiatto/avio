import sys, os, tempfile, json, io, urllib.request, urllib.error
from types import SimpleNamespace as NS
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp; os.environ["HOME"] = tmp; os.environ["XDG_DATA_HOME"] = tmp
for k in ("OPENCODE_API_KEY", "OPENCODE_BASE_URL", "OPENCODE_MODEL", "ANTHROPIC_API_KEY"): os.environ.pop(k, None)
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import ai_client
from ai_client import fetch_models, ModelIds, _is_openrouter

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

G, EU, US = "https://openrouter.ai/api/v1", "https://eu.openrouter.ai/api/v1", "https://us.openrouter.ai/api/v1"
KEY = "sk-or-SECRET-WORKSPACE-KEY"

check("host check: openrouter and its regional subdomains", all(_is_openrouter(u) for u in (G, EU, US, "https://OpenRouter.ai/x")))
check("host check: lookalikes and other providers are not OpenRouter",
      not any(_is_openrouter(u) for u in ("https://evilopenrouter.ai/api/v1", "https://openrouter.ai.evil.example/v1",
                                           "https://us.openrouter.ai.evil.example/v1", "https://api.openai.com/v1", "", None)))

class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass

seen = {}
def http_err(code, message=""):
    body = json.dumps({"error": {"message": message, "code": code}}).encode()
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body))
def install(payload=None, exc=None, key_exc=None):
    """exc applies to /models/user, key_exc to the /key check that runs first."""
    seen["log"] = []
    def fake(req, timeout=None):
        path = req.full_url.split("/api/v1")[-1]
        seen["log"].append(path)
        if path == "/key":
            seen["key_auth"] = req.get_header("Authorization")
            if key_exc: raise key_exc
            return Resp(b'{"data": {"label": "avio"}}')
        seen["url"] = req.full_url; seen["auth"] = req.get_header("Authorization"); seen["n"] = seen.get("n", 0) + 1
        if exc: raise exc
        return Resp(json.dumps(payload).encode())
    urllib.request.urlopen = fake
real_urlopen = urllib.request.urlopen
class FakeOpenAI:                         # the ordinary SDK path: /models with the key
    calls = 0
    def __init__(self, **kw): FakeOpenAI.kw = kw
    @property
    def models(self):
        FakeOpenAI.calls += 1
        return NS(list=lambda: NS(data=[NS(id="z/plain-list", model_extra=None), NS(id="a/another", model_extra=None)]))
real_openai = ai_client.openai.OpenAI
ai_client.openai.OpenAI = FakeOpenAI

catalog = {"data": [{"id": "google/gemma-4-31b-it"}, {"id": "anthropic/claude-sonnet-5.5"},
                    {"id": "openai/text-embedding-3-small"}, {"id": "openai/gpt-6.1-sol"}, "junk", {"nope": 1}]}

# ---- the workspace list ------------------------------------------------------------------------------
install(catalog)
ids = fetch_models(KEY, US)
check("OpenRouter US: asks /models/user on the US address with the key as a bearer token",
      seen["url"] == "https://us.openrouter.ai/api/v1/models/user" and seen["auth"] == f"Bearer {KEY}", str(seen))
check("workspace list: scope is 'workspace' and it is a ModelIds list", isinstance(ids, ModelIds) and ids.scope == "workspace")
check("workspace list: non-chat ids filtered, junk skipped, sorted",
      list(ids) == ["anthropic/claude-sonnet-5.5", "google/gemma-4-31b-it", "openai/gpt-6.1-sol"], str(list(ids)))
check("workspace list: the ordinary SDK /models call was not needed", FakeOpenAI.calls == 0)
fetch_models(KEY, G); check("global address uses /models/user too", seen["url"] == "https://openrouter.ai/api/v1/models/user")
fetch_models(KEY, EU + "/"); check("a trailing slash is handled", seen["url"] == "https://eu.openrouter.ai/api/v1/models/user", seen["url"])

# ---- fallbacks ----------------------------------------------------------------------------------------------
for name, exc in (("403 (e.g. a guardrail refusing the address)", urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"{}"))),
                  ("a network error", urllib.error.URLError("down")),
                  ("a 500", urllib.error.HTTPError("u", 500, "err", {}, io.BytesIO(b"")))):
    install(exc=exc); FakeOpenAI.calls = 0
    ids = fetch_models(KEY, US)
    check(f"fallback to the ordinary list on {name}", list(ids) == ["a/another", "z/plain-list"] and ids.scope == "" and FakeOpenAI.calls == 1, f"{list(ids)} {ids.scope} {FakeOpenAI.calls}")
install(payload="not a dict"); FakeOpenAI.calls = 0
ids = fetch_models(KEY, US)
check("fallback when the response is not the expected JSON", ids.scope == "" and FakeOpenAI.calls == 1)

# ---- the key is checked before the list is called the workspace's ------------------------------------------------
install(catalog); FakeOpenAI.calls = 0
fetch_models(KEY, US)
check("the key is checked first: GET /key, then /models/user, both with the bearer key",
      seen["log"] == ["/key", "/models/user"] and seen["key_auth"] == f"Bearer {KEY}" and seen["auth"] == f"Bearer {KEY}", str(seen["log"]))

install(catalog, key_exc=http_err(401, "No auth credentials found")); FakeOpenAI.calls = 0
try:
    fetch_models("sk-or-mistyped", US); check("a rejected key raises", False, "no error")
except RuntimeError as e:
    check("a rejected key (401) is reported plainly, not labelled as a workspace list",
          "rejected this API key" in str(e) and "401" in str(e), str(e))
check("a rejected key stops before the model list is read", seen["log"] == ["/key"] and FakeOpenAI.calls == 0, str(seen["log"]))

region_msg = ("This request arrived on the global data region, but the key's workspace permits requests only on these "
              "OpenRouter hostnames: us.openrouter.ai. Use one of the permitted hostnames or update the workspace guardrail allowed data regions.")
install(catalog, key_exc=http_err(403, region_msg))
try:
    fetch_models(KEY, G); check("a guardrail region refusal raises", False, "no error")
except RuntimeError as e:
    m = str(e)
    check("a region refusal at Settings time explains itself and both fixes",
          "only accepts requests through US" in m and "Global address (openrouter.ai)" in m and "set this connection's OpenRouter region to US" in m, m)
check("a region refusal stops before the model list too", seen["log"] == ["/key"], str(seen["log"]))
plan_msg = ("Regional routing requires a Business or Enterprise plan. Upgrade at https://openrouter.ai/settings/manage-plan, "
            "then send requests to eu.openrouter.ai or us.openrouter.ai.")
install(catalog, key_exc=http_err(403, plan_msg))
try:
    fetch_models(KEY, US); check("a plan refusal at Settings time raises", False, "no error")
except RuntimeError as e:
    check("a plan refusal at Settings time names the plan, not a guardrail",
          "plan doesn't include US routing" in str(e) and "set this connection's region to Global" in str(e) and "almost always" not in str(e), str(e))
check("a plan refusal stops before the model list", seen["log"] == ["/key"], str(seen["log"]))
install(catalog, key_exc=http_err(403, ""));
try:
    fetch_models(KEY, US); check("a 403 with no message raises", False, "no error")
except RuntimeError as e:
    check("a 403 with no message still points at the guardrails", "guardrail" in str(e) and "OpenRouter refused" in str(e), str(e))

for name, kexc in (("a 500", http_err(500)), ("a 404", http_err(404)), ("a network error", urllib.error.URLError("down")), ("a timeout", TimeoutError("slow"))):
    install(catalog, key_exc=kexc); FakeOpenAI.calls = 0
    ids = fetch_models(KEY, US)
    check(f"{name} on /key is ignored and the workspace list is still read", ids.scope == "workspace" and len(ids) == 3, f"{ids.scope} {list(ids)}")

install(catalog, key_exc=http_err(401)); seen["log"] = []
fetch_models_ok = True
try:
    fetch_models("sk-openai", "https://api.openai.com/v1")
except Exception:
    fetch_models_ok = False
check("non-OpenRouter providers never call /key", seen["log"] == [] and fetch_models_ok, str(seen["log"]))

install({"data": []})
try:
    fetch_models(KEY, US); check("empty workspace list raises", False, "no error")
except RuntimeError as e:
    check("an empty workspace list says the guardrails allow nothing", "allows no models" in str(e) and "guardrails" in str(e), str(e))

# ---- other providers are untouched --------------------------------------------------------------------------
install(catalog); seen.clear(); FakeOpenAI.calls = 0
ids = fetch_models("sk-openai", "https://api.openai.com/v1")
check("OpenAI: the plain /models call, no OpenRouter request, scope empty", FakeOpenAI.calls == 1 and "n" not in seen and ids.scope == "", f"{FakeOpenAI.calls} {seen}")
check("the key is passed to the SDK client as before", FakeOpenAI.kw.get("api_key") == "sk-openai")
ids = fetch_models("sk-x", "https://evilopenrouter.ai/api/v1")
check("a lookalike host is treated as an ordinary provider", "n" not in seen and ids.scope == "")

# ---- /api/models reports the scope ---------------------------------------------------------------------------
import main
from fastapi.testclient import TestClient
main.connections.get_connection = lambda cid: None
tc = TestClient(main.app)
wl = ModelIds(["a/b"]); wl.scope = "workspace"
main.fetch_models = lambda key, url: wl
r = tc.post("/api/models", json={"api_key": KEY, "base_url": US}).json()
check("api: /api/models passes the workspace scope to the UI", r["source"] == "live" and r["scope"] == "workspace" and r["models"] == [{"id": "a/b", "label": "a/b"}], str(r))
main.fetch_models = lambda key, url: ["x/y"]
r = tc.post("/api/models", json={"api_key": "k", "base_url": "https://api.openai.com/v1"}).json()
check("api: a plain list has an empty scope", r["scope"] == "" and r["source"] == "live", str(r))
def boom(key, url): raise RuntimeError("Your OpenRouter workspace allows no models. Check its guardrails")
main.fetch_models = boom
r = tc.post("/api/models", json={"api_key": KEY, "base_url": US}).json()
check("api: an empty workspace falls back to the built-in list and says why", r["source"] == "fallback" and "allows no models" in r["error"], str(r)[:200])
check("api: the key never appears in any response", KEY not in json.dumps(r))

urllib.request.urlopen = real_urlopen; ai_client.openai.OpenAI = real_openai
print("\nfailures:", fails)
sys.exit(1 if fails else 0)
