import os, sys, json, tempfile
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp                       # isolate Avio config / skills from the real ones
os.environ.pop("OPENCODE_MAX_TOKENS", None)
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

try:
    import httpx2 as httpx      # openai 3.x ships on httpx2
except ImportError:
    import httpx
import openai
import ai_client, sf_skills
from ai_client import AIClient, StreamFinish

fails = 0
def check(name, cond, detail=""):
    global fails
    fails += (not cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail and not cond else ""))

def bad_request(msg):
    req = httpx.Request("POST", "http://x/v1/chat/completions")
    return openai.BadRequestError(msg, response=httpx.Response(400, request=req), body=None)

# ---- fake OpenAI client -------------------------------------------------------
class FakeCompletions:
    def __init__(self, behaviours): self.calls = []; self.behaviours = list(behaviours)
    def create(self, **kw):
        self.calls.append(kw)
        b = self.behaviours.pop(0) if self.behaviours else "ok"
        if isinstance(b, Exception): raise b
        if b == "ok": return "RESPONSE"
        return b
class FakeClient:
    def __init__(self, behaviours): self.chat = type("C", (), {"completions": FakeCompletions(behaviours)})()

def client_with(behaviours, base_url):
    ai = AIClient()
    fake = FakeClient(behaviours)
    ai._client_for = lambda r: fake                  # bypass the SDK client cache
    ai._r = ai_client.Resolved(base_url, "m", "k")
    return ai, fake.chat.completions

# ---- _prepare -----------------------------------------------------------------
full = AIClient._prepare([{"role": "user", "content": "hi", "system": True, "truncated": True},
                          {"role": "assistant", "content": "yo", "extra": 1}], "SYS")
check("prepare: system first, extra keys stripped",
      full == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}], str(full))

# ---- max tokens defaults --------------------------------------------------------
ai_client._load_avio_config = lambda: {}
check("max_tokens: cloud default 16384", ai_client._load_max_tokens("https://api.anthropic.com/v1") == 16384)
check("max_tokens: local default 4096", ai_client._load_max_tokens("http://localhost:11434/v1") == 4096)
ai_client._load_avio_config = lambda: {"max_tokens": 9000}
check("max_tokens: config.json override", ai_client._load_max_tokens("https://api.openai.com/v1") == 9000)
os.environ["OPENCODE_MAX_TOKENS"] = "1234"
check("max_tokens: env override beats config", ai_client._load_max_tokens("https://x/v1") == 1234)
os.environ["OPENCODE_MAX_TOKENS"] = "junk"
check("max_tokens: bad env value ignored", ai_client._load_max_tokens("https://x/v1") == 9000)
del os.environ["OPENCODE_MAX_TOKENS"]; ai_client._load_avio_config = lambda: {}

# ---- _create: parameter name + ladder ----------------------------------------------
ai, calls = client_with(["ok"], "https://api.openai.com/v1")
ai._create(ai._r, "m", [], 16384, False)
check("openai.com uses max_completion_tokens first", "max_completion_tokens" in calls.calls[0] and "max_tokens" not in calls.calls[0])

ai, calls = client_with(["ok"], "https://api.anthropic.com/v1")
ai._create(ai._r, "m", [], 16384, False)
check("other providers use max_tokens", "max_tokens" in calls.calls[0] and "max_completion_tokens" not in calls.calls[0])

ai, calls = client_with([bad_request("max_tokens is too large: 16384. This model supports at most 4096 completion tokens."),
                         bad_request("max_tokens: 8192 > 4096, which is the maximum allowed"), "ok"], "https://gw/v1")
r = ai._create(ai._r, "m", [], 16384, False)
used = [c.get("max_tokens") for c in calls.calls]
check("too-large limit walks the ladder 16384 -> 8192 -> 4096", r == "RESPONSE" and used == [16384, 8192, 4096], str(used))

ai, calls = client_with([bad_request("Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."), "ok"], "https://gw/v1")
ai._create(ai._r, "m", [], 4096, False)
check("unsupported max_tokens switches to max_completion_tokens",
      "max_tokens" in calls.calls[0] and "max_completion_tokens" in calls.calls[1] and "max_tokens" not in calls.calls[1], str(calls.calls))

ai, calls = client_with([bad_request("Invalid value for 'model': nope")], "https://gw/v1")
try: ai._create(ai._r, "m", [], 4096, False); raised = False
except openai.BadRequestError: raised = True
check("unrelated 400 is re-raised, not retried", raised and len(calls.calls) == 1)

ai, calls = client_with([bad_request("max_tokens too large")] * 6, "https://gw/v1")
try: ai._create(ai._r, "m", [], 2048, False); raised = False
except openai.BadRequestError: raised = True
check("ladder exhausted -> original error raised", raised, f"calls={len(calls.calls)}")

# ---- stream(): finish reason + empty-choices chunk --------------------------------------
class Delta:  # chunk helpers
    def __init__(self, text): self.content = text
class Choice:
    def __init__(self, text=None, finish=None): self.delta = Delta(text); self.finish_reason = finish
class Chunk:
    def __init__(self, choices): self.choices = choices
class Stream:
    def __init__(self, chunks): self.chunks = chunks
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __iter__(self): return iter(self.chunks)

def run_stream(chunks):
    ai, calls = client_with([Stream(chunks)], "https://gw/v1")
    return list(ai.stream([{"role": "user", "content": "q", "system": True}], system="S", model="m", resolved=ai._r)), calls

out, calls = run_stream([Chunk([]), Chunk([Choice("Hel")]), Chunk([Choice("lo")]), Chunk([Choice(None, "length")]), Chunk([])])
check("stream: deltas then StreamFinish(length), empty-choices chunks skipped",
      out[:2] == ["Hel", "lo"] and isinstance(out[2], StreamFinish) and out[2].truncated and len(out) == 3, str(out))
check("stream: request sent role/content only", all(set(m) == {"role", "content"} for m in calls.calls[0]["messages"]))
out, _ = run_stream([Chunk([Choice("ok")]), Chunk([Choice(None, "stop")])])
check("stream: normal stop is not truncated", isinstance(out[-1], StreamFinish) and not out[-1].truncated and out[-1].reason == "stop")

# ---- /api/ai/chat SSE ---------------------------------------------------------------------
from fastapi.testclient import TestClient
import main
seen = {}
def fake_aug(system, messages, force=None, local=False):
    seen["local"] = local; return (system or ""), ["Fake Skill"]
main.augment_with_skills = fake_aug
import connections as _cn
main.connections.resolve = lambda cid=None: ai_client.Resolved("http://localhost:11434/v1", "llama3:8b", "")
def fake_stream(messages, system=None, model=None, resolved=None, request_id=None):
    yield "partial"; yield StreamFinish("length")
main._ai.stream = fake_stream
tc = TestClient(main.app)
r = tc.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}], "system": "S"})
lines = [l for l in r.text.splitlines() if l.startswith("data: ")]
check("SSE: skills event first, then delta, truncated event, [DONE]", lines == ['data: {"skills": ["Fake Skill"]}', 'data: {"delta": "partial"}', 'data: {"truncated": true}', 'data: [DONE]'], str(lines))
check("chat endpoint passes local=True to augment_system", seen.get("local") is True)
def fake_stream2(messages, system=None, model=None, resolved=None, request_id=None):
    yield "x"; yield StreamFinish("stop")
main._ai.stream = fake_stream2
r = tc.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
check("SSE: no truncated event on a normal stop", "truncated" not in r.text and r.text.strip().endswith("data: [DONE]"))

# ---- skills: condensed mode ---------------------------------------------------------------
apex_full = sf_skills._load_file_local(sf_skills.SKILLS_DIR, "platform-apex-generate/SKILL.md")
c = sf_skills._condense(apex_full, 6000)
check("condense: YAML header removed", "relatedSkills" not in c and not c.startswith("---"))
check("condense: starts at the Rules section", c.startswith("## Rules"), c[:40])
check("condense: within budget (+ marker)", len(c) <= 6000 + 60, str(len(c)))
check("condense: keeps hard-stop constraints", "Hard-Stop Constraints" in c)
check("condense: ends with the condensed marker at a boundary", c.rstrip().endswith("[... condensed for a small context window ...]"))
check("condense: short text returned whole", sf_skills._condense("# T\n\nshort", 6000) == "# T\n\nshort")

msgs = [{"role": "user", "content": "x"}]
full_sys = sf_skills.augment_system("SYS", msgs, ["platform-apex-generate"])
loc_sys = sf_skills.augment_system("SYS", msgs, ["platform-apex-generate"], local=True)
check("cloud: full skill (~23k chars)", len(full_sys) > 20000, str(len(full_sys)))
check("local: condensed (<9k chars, ~2k tokens)", 3000 < len(loc_sys) < 9000, str(len(loc_sys)))
check("local: says condensed, no YAML header", "condensed for a small context window" in loc_sys and "relatedSkills" not in loc_sys)
both = sf_skills.augment_system("SYS", [{"role": "user", "content": "write a soql query in apex"}], None, local=True)
check("local: two skills share the budget (<9k chars)", "platform-apex-generate" in both and "platform-soql-query" in both and len(both) < 9000, str(len(both)))

# config-driven budgets
sf_skills._load_skills_config = lambda: {"enabled": True, "source": "bundled", "path": None, "url": None, "inject": "relevant", "local_budget": 0}
check("skills_local_budget=0: no skills for local models", sf_skills.augment_system("SYS", msgs, ["platform-apex-generate"], local=True) == "SYS")
check("skills_local_budget=0: cloud unaffected", len(sf_skills.augment_system("SYS", msgs, ["platform-apex-generate"], local=False)) > 20000)
sf_skills._load_skills_config = lambda: {"enabled": True, "source": "bundled", "path": None, "url": None, "inject": "relevant", "local_budget": -1}
check("skills_local_budget=-1: local gets the full skill", len(sf_skills.augment_system("SYS", msgs, ["platform-apex-generate"], local=True)) > 20000)
sf_skills._load_skills_config = lambda: {"enabled": True, "source": "bundled", "path": None, "url": None, "inject": "relevant", "local_budget": "garbage"}
check("skills_local_budget garbage -> default", 3000 < len(sf_skills.augment_system("SYS", msgs, ["platform-apex-generate"], local=True)) < 9000)

print("\nfailures:", fails)
sys.exit(1 if fails else 0)
