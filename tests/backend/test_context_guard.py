import sys, os, tempfile, json, io, urllib.request
from types import SimpleNamespace as NS
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp; os.environ["HOME"] = tmp; os.environ["XDG_DATA_HOME"] = tmp
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import openai, ai_client, sf_skills
from ai_client import Resolved, describe_error, is_context_length_error, ProviderStreamError

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

def err(status, message, code=None):
    resp = NS(status_code=status, headers={}, request=None)
    cls = {400: openai.BadRequestError, 413: openai.APIStatusError, 429: openai.RateLimitError}.get(status, openai.APIStatusError)
    body = {"error": {"message": message, "code": code}}
    return cls(f"Error code: {status}", response=resp, body=body)

# Skills: bundled, no added skills, no network.
sf_skills.USER_SKILLS = __import__("pathlib").Path(tmp) / "skills"
sf_skills._load_skills_config = lambda: {"enabled": True, "source": "bundled", "path": None, "url": None,
    "custom_skills": [], "inject": "relevant", "local_budget": sf_skills.LOCAL_SKILL_BUDGET}
cfg = {}
ai_client._load_avio_config = lambda: dict(cfg)

# ---- error detection --------------------------------------------------------------------------
check("detect: OpenAI 'maximum context length' 400", is_context_length_error(err(400, "This model's maximum context length is 8192 tokens.")))
check("detect: code context_length_exceeded", is_context_length_error(err(400, "too long", "context_length_exceeded")))
check("detect: Anthropic 'prompt is too long'", is_context_length_error(err(400, "prompt is too long: 210000 tokens > 200000 maximum")))
check("detect: Groq 413 'Request too large'", is_context_length_error(err(413, "Request too large for model llama-3.1-8b-instant")))
check("detect: in-stream error", is_context_length_error(ProviderStreamError(400, "maximum context length exceeded")))
check("not: other 400", not is_context_length_error(err(400, "Invalid model id")))
check("not: 429 even with the words", not is_context_length_error(err(429, "Request too large")))
check("not: 500", not is_context_length_error(err(500, "maximum context length")))

R = Resolved("https://openrouter.ai/api/v1", "small/model", "SECRETKEY")
m = describe_error(err(400, "This model's maximum context length is 8192 tokens."), R, "small/model")
check("message: plain explanation", "context of small/model is too small for this prompt plus Avio's Salesforce skills" in m, m)
check("message: what to do", "larger context" in m and "shorten the conversation" in m, m)
check("message: provider text kept", "maximum context length is 8192" in m and "SECRETKEY" not in m, m)

# ---- context length lookup ----------------------------------------------------------------------
ai_client._CONTEXT_LENGTHS.clear(); ai_client._CONTEXT_FETCHED.clear()
ai_client._remember_contexts("https://openrouter.ai/api/v1/", [{"id": "a/b", "context_length": 8192}, {"id": "c", "context_window": 32768},
    {"id": "d", "limit": {"context": 200000, "input": 100000, "output": 32000}}, {"id": "e"}, "junk"])
check("lookup: context_length", ai_client.model_context_length(Resolved("https://openrouter.ai/api/v1", "a/b", "k")) == 8192)
check("lookup: context_window", ai_client.model_context_length(Resolved("https://openrouter.ai/api/v1", "c", "k")) == 32768)
check("lookup: OpenCode limit (input+output when smaller)", ai_client.model_context_length(Resolved("https://openrouter.ai/api/v1", "d", "k")) == 132000)

class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass
seen = []
real_open = urllib.request.urlopen
def fake_open(req, timeout=None):
    seen.append((req.full_url, dict(req.headers)))
    return Resp(json.dumps({"data": [{"id": "x/y", "context_length": 4096}]}).encode())
urllib.request.urlopen = fake_open
n = ai_client.model_context_length(Resolved("https://openrouter.ai/api/v1", "x/y", "SECRETKEY"))
n2 = ai_client.model_context_length(Resolved("https://openrouter.ai/api/v1", "zz", "SECRETKEY"))
check("lazy: OpenRouter catalog read once, without the key", n == 4096 and len(seen) == 1 and "Authorization" not in seen[0][1], str(seen))
check("lazy: unknown model -> None, no second read within the hour", n2 is None and len(seen) == 1, str(seen))
check("lazy: other providers never read", ai_client.model_context_length(Resolved("https://api.openai.com/v1", "gpt-x", "k")) is None and len(seen) == 1)
check("lazy: local never read", ai_client.model_context_length(Resolved("http://localhost:11434/v1", "llama", "")) is None and len(seen) == 1)
urllib.request.urlopen = real_open

# fetch_models records context lengths (OpenRouter workspace list)
ai_client._CONTEXT_LENGTHS.clear()
urllib.request.urlopen = lambda req, timeout=None: Resp(json.dumps({"data": [{"id": "w/m", "context_length": 65536}]}).encode())
ai_client._fetch_openrouter_workspace_models("https://openrouter.ai/api/v1", "k")
urllib.request.urlopen = real_open
check("fetch: /models/user context_length remembered", ai_client._CONTEXT_LENGTHS.get(("https://openrouter.ai/api/v1", "w/m")) == 65536)

# ---- proactive guard through the real endpoint ----------------------------------------------------
from fastapi.testclient import TestClient
import main
RES = Resolved("https://api.example.com/v1", "m", "k")
main.connections.resolve = lambda cid=None: RES
CTX = {}
main.model_context_length = lambda r, model=None: CTX.get(model or r.model)
calls = []
script = []      # per call: "ok" or an exception to raise before any text, or ("mid", exc)
def fake_stream(messages, system=None, model=None, resolved=None, request_id=None):
    calls.append(system)
    step = script.pop(0) if script else "ok"
    if isinstance(step, tuple):
        yield "partial "
        raise step[1]
    if isinstance(step, Exception):
        raise step
    yield "ok"
main._ai.stream = fake_stream
tc = TestClient(main.app)
APEX = ["platform-apex-generate"]
def run(model="m", text="Create an Apex service class", steps=()):
    calls.clear(); script[:] = list(steps)
    r = tc.post("/api/ai/chat", json={"messages": [{"role": "user", "content": text}], "system": "S",
                                      "force_skills": APEX, "model": model})
    return [json.loads(l[6:]) if l[6:] != "[DONE]" else "DONE" for l in r.text.splitlines() if l.startswith("data: ")]

full_len = len(sf_skills.augment_with_skills("S", [{"role": "user", "content": "x"}], APEX)[0])
print(f"INFO full Apex system prompt {full_len} chars (~{full_len // 4} tokens)")

ev = run("unknown")
check("unknown context -> unchanged (full skills, no guard mark)", ev[0].get("skills") == ["Apex Generate"] and "skills_guard" not in ev[0]
      and "Skill file:" in calls[0], str(ev[0]))

CTX["big"] = 1_000_000
ev = run("big")
check("huge context -> full skills", ev[0].get("skills") == ["Apex Generate"] and len(calls[0]) >= full_len - 10, str(ev[0]))

CTX["small"] = 32_000      # 0.85*32000 - 16384 = 10816 tokens of room: full (~23k tokens) no, condensed (~1.5k) yes
ev = run("small")
check("small context -> condensed, marked in the skills event", ev[0].get("skills") == ["Apex Generate (condensed: model context too small)"]
      and ev[0].get("skills_guard") == "condensed", str(ev[0]))
check("small context -> condensed text sent (no templates)", "Skill file:" not in calls[0] and "SALESFORCE SKILL REFERENCE" in calls[0] and len(calls[0]) < 10000, len(calls[0]))

CTX["tiny"] = 20_000       # room = 17000 - 16384 = 616 tokens: even condensed does not fit
ev = run("tiny")
check("tiny context -> skills dropped", ev[0].get("skills") == ["none (model context too small for skills)"] and ev[0].get("skills_guard") == "dropped", str(ev[0]))
check("tiny context -> system prompt is the panel's own", calls[0] == "S", calls[0][:80])

cfg["skills_context_guard"] = False
ev = run("tiny")
check("guard off -> full skills even for a tiny context", ev[0].get("skills") == ["Apex Generate"] and "Skill file:" in calls[0], str(ev[0]))
cfg.pop("skills_context_guard")

calls.clear()
r = tc.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "what is the weather"}], "system": "S", "model": "tiny"})
first = json.loads([l for l in r.text.splitlines() if l.startswith("data: ")][0][6:])
check("no skills detected -> guard does nothing", first == {"skills": []} and calls[0] == "S", str(first))

# ---- reactive retry ----------------------------------------------------------------------------
CTX.clear()
ctx_err = err(400, "This model's maximum context length is 8192 tokens. However, you requested 30000 tokens.", "context_length_exceeded")
ev = run("m", steps=[ctx_err, "ok"])
check("reactive: retried once with condensed skills", len(calls) == 2 and "Skill file:" in calls[0] and "Skill file:" not in calls[1]
      and "SALESFORCE SKILL REFERENCE" in calls[1], [len(c) for c in calls])
check("reactive: second skills event marks condensed", ev[1].get("skills_guard") == "condensed"
      and ev[1]["skills"] == ["Apex Generate (condensed: model context too small)"], str(ev[:3]))
check("reactive: reply streamed and finished", {"delta": "ok"} in ev and ev[-1] == "DONE" and not any("error" in e for e in ev if isinstance(e, dict)), str(ev))

ev = run("m", steps=[ctx_err, ctx_err])
errs = [e["error"] for e in ev if isinstance(e, dict) and "error" in e]
check("reactive: only one retry", len(calls) == 2, len(calls))
check("reactive: second failure -> plain context message", errs and "too small for this prompt plus Avio's Salesforce skills" in errs[0]
      and "larger context" in errs[0], str(errs))

ev = run("m", steps=[("mid", ctx_err)])
errs = [e["error"] for e in ev if isinstance(e, dict) and "error" in e]
check("reactive: never retries after text streamed", len(calls) == 1 and {"delta": "partial "} in ev and errs, str(ev))

ev = run("m", steps=[err(400, "Invalid model id")])
check("reactive: other 400 not retried", len(calls) == 1 and any("error" in e for e in ev if isinstance(e, dict)), str(ev))

CTX["small"] = 32_000
ev = run("small", steps=[ctx_err, "ok"])
check("reactive after proactive condense: retry drops skills", len(calls) == 2 and calls[1] == "S" and ev[1].get("skills_guard") == "dropped", str(ev[:3]))
CTX.clear()

cfg["skills_context_guard"] = False
ev = run("m", steps=[ctx_err, "ok"])
check("guard off -> no retry, plain message", len(calls) == 1 and any("too small" in e.get("error", "") for e in ev if isinstance(e, dict)), str(ev))
cfg.pop("skills_context_guard")

# local provider: retry goes straight to no skills (its text is already condensed)
RES = Resolved("http://localhost:11434/v1", "llama", "")
main.connections.resolve = lambda cid=None: RES
ev = run("llama", steps=[ctx_err, "ok"])
check("local: retry drops skills", len(calls) == 2 and calls[1] == "S" and ev[1].get("skills_guard") == "dropped", str(ev[:3]))

print("\nfailures:", fails)
sys.exit(1 if fails else 0)
