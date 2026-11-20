import sys, os, tempfile, json, pathlib
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp
os.environ["HOME"] = tmp
os.environ["XDG_DATA_HOME"] = tmp
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import sf_skills

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

# isolated added-skills folder + bundled built-ins, no network
sf_skills.USER_SKILLS = pathlib.Path(tmp) / "skills"
sf_skills._load_skills_config = lambda: {"enabled": True, "source": "bundled", "path": None, "url": None,
    "inject": "relevant", "local_budget": sf_skills.LOCAL_SKILL_BUDGET}
def add(folder, name, body="RULES for " ):
    d = sf_skills.USER_SKILLS / folder; d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body + folder, encoding="utf-8")
    (d / ".avio_skill_meta.json").write_text(json.dumps({"name": name}), encoding="utf-8")
add("apex-test-generate", "Apex Test Generate")
add("apex-debug-logs", "Apex Debug Logs")
add("automation-flow-generate", "Automation Flow Generate")
add("apex-guide", "Apex Guide")                       # named only with a domain word
add("platform-skill", "Platform Skill")               # no topic words at all (all stopwords)

msg = lambda t: [{"role": "user", "content": t}]
def names(text, force=None, local=False):
    return sf_skills.augment_with_skills("SYS", msg(text), force, local)[1]
APEX = ["platform-apex-generate"]; SOQL = ["platform-soql-query"]

# ---- (b) relevance ---------------------------------------------------------------------------
n = names("Create an Apex test class for Account creation", APEX)
check("test prompt loads Apex Test Generate", "Apex Test Generate" in n, str(n))
check("test prompt does NOT load Apex Debug Logs", "Apex Debug Logs" not in n, str(n))
n = names("help me read this debug log", APEX)
check("debug-log prompt loads Apex Debug Logs", "Apex Debug Logs" in n, str(n))
check("debug-log prompt does NOT load Apex Test Generate", "Apex Test Generate" not in n, str(n))
n = names("anything at all", APEX)
check("domain-only skill (Apex Guide) loads in the Apex panel", "Apex Guide" in n, str(n))
check("skill with no topic words always loads", "Platform Skill" in n, str(n))
check("unrelated skill (flow) not loaded for an apex prompt", "Automation Flow Generate" not in n, str(n))
check("'build a flow' loads the flow skill", "Automation Flow Generate" in names("build a flow for onboarding"))
n = names("what is the weather today")
check("unrelated prompt loads only the no-topic skill", n == ["Platform Skill"], str(n))
check("_qualifies: specific word wins over domain word", sf_skills._qualifies(["apex", "debu", "logs"], "apex test") is False)
check("_qualifies: domain-only skill uses the domain word", sf_skills._qualifies(["apex"], "apex test") is True)

# ---- (a) SOQL runner forcing ---------------------------------------------------------------------
prompt = "open opportunities over 100000 with account name"
check("without force: no SOQL skill for a keyword-less prompt", "SOQL Query" not in names(prompt) and "platform-soql-query" not in names(prompt))
n = names(prompt, SOQL)
check("with force: SOQL skill injected", any("soql" in x.lower() for x in n), str(n))
out, n2 = sf_skills.augment_with_skills("SYS", msg(prompt), SOQL)
check("forced SOQL guidance is in the system text", "SALESFORCE SKILL REFERENCE" in out and "platform-soql-query" in out)

# ---- (c) names reported ------------------------------------------------------------------------
out, n = sf_skills.augment_with_skills("SYS", msg("hello"), None)
check("nothing relevant -> no built-in names, text unchanged for built-ins", not any("platform-" in x for x in n) and "SALESFORCE SKILL REFERENCE" not in out)
out, n = sf_skills.augment_with_skills("SYS", msg("hello"), APEX)
check("built-in name is a friendly label", n[0] == "Apex Generate", str(n))
out, n = sf_skills.augment_with_skills("SYS", msg("hello"), APEX, local=True)
check("local mode marks the built-in as condensed", n and n[0].endswith("(condensed)"), str(n))
sf_skills._load_skills_config = lambda: {"enabled": False, "source": "bundled", "path": None, "url": None,
    "inject": "relevant", "local_budget": 6000}
out, n = sf_skills.augment_with_skills("SYS", msg("apex test"), APEX)
check("skills disabled -> unchanged and []", out == "SYS" and n == [], str(n))
sf_skills._load_skills_config = lambda: {"enabled": True, "source": "bundled", "path": None, "url": None,
    "inject": "relevant", "local_budget": 0}
out, n = sf_skills.augment_with_skills("SYS", msg("apex test"), APEX, local=True)
check("local budget 0 -> unchanged and []", out == "SYS" and n == [], str(n))
check("augment_system wrapper returns just the string", isinstance(sf_skills.augment_system("SYS", msg("x"), None), str))

# names always match what is in the text
sf_skills._load_skills_config = lambda: {"enabled": True, "source": "bundled", "path": None, "url": None,
    "inject": "relevant", "local_budget": 6000}
out, n = sf_skills.augment_with_skills("SYS", msg("write a test class"), APEX)
check("every reported added skill is really in the text", all(("## " + x) in out for x in n if "(" not in x and x != "Apex Generate"), str(n))

# ---- keyless OpenCode listing (no network: patch the fetcher) ---------------------------------
import ai_client
calls = {}
def fake_public(url): calls["url"] = url; return ["gemini-3.5-flash", "models/claude-x", "text-embedding-3-small"]
ai_client._fetch_public_model_ids = fake_public
ids = ai_client.fetch_models(None, ai_client.OPENCODE_GATEWAY_URL)
check("OpenCode with no key lists the public catalog", calls.get("url") and "gemini-3.5-flash" in ids, str(ids))
check("catalog ids are filtered and prefix-stripped", "claude-x" in ids and "text-embedding-3-small" not in ids, str(ids))
calls.clear()
try:
    ai_client.fetch_models(None, "https://api.openai.com/v1")
    check("OpenAI with no key still raises", False, "no exception")
except Exception:
    check("OpenAI with no key still raises", not calls)

# ---- real endpoints emit the skills event first (no fakes for augmentation) ---------------------
from fastapi.testclient import TestClient
import main
main.connections.resolve = lambda cid=None: ai_client.Resolved("https://api.example.com/v1", "m", "k")
def fake_stream(messages, system=None, model=None, resolved=None, request_id=None):
    fake_stream.system = system
    yield "ok"
main._ai.stream = fake_stream
tc = TestClient(main.app)
for path in ("/api/ai/chat", "/api/claude/chat"):
    r = tc.post(path, json={"messages": msg("Create an Apex test class"), "system": "S", "force_skills": APEX})
    lines = [l for l in r.text.splitlines() if l.startswith("data: ")]
    first = json.loads(lines[0][6:])
    check(f"{path}: first SSE event lists the injected skills",
          first.get("skills") and "Apex Generate" in first["skills"] and "Apex Test Generate" in first["skills"]
          and "Apex Debug Logs" not in first["skills"], str(first))
    check(f"{path}: system text really contains what was reported", "Apex Test Generate" in fake_stream.system)
r = tc.post("/api/claude/chat", json={"messages": msg("what is the weather today"), "system": "S"})
first = json.loads([l for l in r.text.splitlines() if l.startswith("data: ")][0][6:])
check("SSE skills event is present (list) even when nothing is injected", isinstance(first.get("skills"), list), str(first))

# ---- free OpenCode models are not listed -------------------------------------------------------
import io, urllib.request
def entry(i, inp, out): return {"id": i, "cost": {"text": {"input": {"price": inp}, "output": {"price": out}}}}
check("free: both prices 0", ai_client._is_free_model(entry("x-free", 0, 0)))
check("paid: input > 0", not ai_client._is_free_model(entry("a", 0.1, 0)))
check("paid: output > 0", not ai_client._is_free_model(entry("a", 0, 0.5)))
check("float zero prices count as free", ai_client._is_free_model(entry("x", 0.0, 0.0)))
check("missing cost -> treated as paid (kept)", not ai_client._is_free_model({"id": "m"}))
check("odd cost shape -> kept", not ai_client._is_free_model({"id": "m", "cost": "free"}) and not ai_client._is_free_model({"id": "m", "cost": {"text": {"input": None}}}))
check("non-numeric price -> kept", not ai_client._is_free_model(entry("m", "abc", "def")))

class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass
catalog = {"object": "list", "data": [entry("claude-haiku-5-5", 0.1, 0.5), entry("big-pickle", 0, 0),
           entry("nemotron-3.5-lightning-free", 0, 0), entry("glm-5.3-flash", 0.15, 0.5), {"id": "no-cost-model"}, {"nope": 1}, "junk"]}
real_urlopen = urllib.request.urlopen
urllib.request.urlopen = lambda req, timeout=None: FakeResp(json.dumps(catalog).encode())
import importlib; importlib.reload(ai_client)          # undo the earlier patch of _fetch_public_model_ids
ids = ai_client.fetch_models(None, ai_client.OPENCODE_GATEWAY_URL)
urllib.request.urlopen = real_urlopen
check("real fetch path drops free models, keeps paid and unpriced", ids == ["claude-haiku-5-5", "glm-5.3-flash", "no-cost-model"], str(ids))

# ---- linked assets (templates) are fetched and injected -----------------------------------------------------------
import shutil, io, urllib.request
saved_user = sf_skills.USER_SKILLS
scratch = pathlib.Path(tmp) / "skills_assets"
sf_skills.USER_SKILLS = scratch
SKILL = """# Generating tests

Use [the template](assets/test-class-template.cls) as the start, and also assets/factory.cls.
See [guide](references/guide.md).
Bad links: [evil](../secret.cls) [abs](/etc/passwd.cls) [url](https://x.example/a.cls)
[script](scripts/run.py) [windows](assets\\\\x.cls)
Big and missing: [big](assets/big.cls) [gone](assets/missing.cls)
"""
def build_skill(root):
    (root / "assets").mkdir(parents=True, exist_ok=True); (root / "references").mkdir(exist_ok=True)
    (root / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (root / "assets" / "test-class-template.cls").write_text("@isTest\nprivate class XTest { /* <!-- keep --> */ }", encoding="utf-8")
    (root / "assets" / "factory.cls").write_text("public class TestDataFactory { }", encoding="utf-8")
    (root / "assets" / "unlinked.cls").write_text("UNLINKED-CONTENT", encoding="utf-8")
    (root / "assets" / "big.cls").write_text("x" * 40000, encoding="utf-8")
    (root / "references" / "guide.md").write_text("GUIDE <!-- hidden --> text", encoding="utf-8")
    (root.parent / "secret.cls").write_text("SECRET-CONTENT", encoding="utf-8")

got = set(sf_skills._linked_paths(SKILL))
check("linked paths: the safe ones, markdown and assets, bare and linked",
      got == {"assets/test-class-template.cls", "assets/factory.cls", "references/guide.md", "assets/big.cls", "assets/missing.cls"}, str(got))
check("linked paths: '..', absolute, URL, script and backslash paths refused", not any(("secret" in p or "passwd" in p or "x.example" in p or "run.py" in p or "x.cls" == p[-5:] and "\\" in p) for p in got), str(got))
check("candidate paths: linked first, fallback markdown names after",
      sf_skills._candidate_ref_paths(SKILL)[:5] == sf_skills._linked_paths(SKILL)[:5] and "references/anti-patterns.md" in sf_skills._candidate_ref_paths(SKILL))
check("linked paths: none for empty/None", sf_skills._linked_paths(None) == [] and sf_skills._linked_paths("") == [])
check("plain markdown links still found", sf_skills._linked_paths("see [a](references/a.md#sec)") == ["references/a.md"])

sk = scratch / "apex-assets"; build_skill(sk)
check("asset reader: ok / outside folder / too big / missing",
      sf_skills._read_linked_asset(sk, "assets/factory.cls") == "public class TestDataFactory { }"
      and sf_skills._read_linked_asset(sk, "../secret.cls") is None
      and sf_skills._read_linked_asset(sk, "assets/big.cls") is None
      and sf_skills._read_linked_asset(sk, "assets/missing.cls") is None)
ctx, names = sf_skills._user_skills("", "all")
check("injected: the linked template, labelled and fenced as Apex",
      "### Skill file: `assets/test-class-template.cls`" in ctx and "````apex\n@isTest\nprivate class XTest" in ctx, ctx[:300])
check("injected: the linked factory template too", "public class TestDataFactory" in ctx and "`assets/factory.cls`" in ctx)
check("injected: code comments are preserved in code files", "<!-- keep -->" in ctx)
check("injected: markdown still strips HTML comments", "GUIDE  text" in ctx and "hidden" not in ctx, ctx)
check("not injected: unlinked, outside-folder, oversize and missing files",
      "UNLINKED-CONTENT" not in ctx and "SECRET-CONTENT" not in ctx and "xxxxxxxx" not in ctx)

# download: fake the network
calls = []
fake_net = {"SKILL.md": SKILL, "assets/test-class-template.cls": "@isTest class T {}", "assets/factory.cls": "class F {}",
            "references/guide.md": "guide", "assets/big.cls": "x" * 40000}
def fake_load(base, rel, use_cache=True): calls.append((rel, use_cache)); return fake_net.get(rel)
real_load = sf_skills._load_file_url
sf_skills._load_file_url = fake_load
dest = scratch / "downloaded"; n = sf_skills._fetch_skill_from_url("https://example.invalid/s", dest)
sf_skills._load_file_url = real_load
files = sorted(str(p.relative_to(dest)).replace("\\", "/") for p in dest.rglob("*") if p.is_file())
check("download: SKILL.md, markdown refs and linked templates written", files == ["SKILL.md", "assets/factory.cls", "assets/test-class-template.cls", "references/guide.md"], str(files))
check("download: oversize asset skipped, count matches", "assets/big.cls" not in files and n == 4, f"{n} {files}")
check("download: always fresh (cache bypassed)", all(uc is False for _, uc in calls))

# comments: stripped from markdown only
class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass
real_open = urllib.request.urlopen
urllib.request.urlopen = lambda url, timeout=None: Resp(b"a <!-- c --> b")
md = sf_skills._load_file_url("https://h.invalid", "r/x.md", use_cache=False)
cls = sf_skills._load_file_url("https://h.invalid", "r/x.cls", use_cache=False)
urllib.request.urlopen = real_open
check("download: HTML comments stripped from .md only", md == "a  b" and cls == "a <!-- c --> b", f"{md!r} {cls!r}")

# local copy
src = pathlib.Path(tmp) / "srcskill"; build_skill(src)
d2 = scratch / "copied"
n = sf_skills._copy_skill_dir(src, d2)
cf = sorted(str(p.relative_to(d2)).replace("\\", "/") for p in d2.rglob("*") if p.is_file())
check("local copy: markdown plus linked assets only", cf == ["SKILL.md", "assets/factory.cls", "assets/test-class-template.cls", "references/guide.md"] and n == 4, f"{n} {cf}")
r = sf_skills.fetch_skill("copy-test", str(src))
check("fetch_skill from a local folder uses the same copy", r["ok"] and r["files"] == 4, str(r))
sf_skills.USER_SKILLS = saved_user

# ---- bundled Apex skill: linked templates are sent in cloud mode (fix 1) -------------------------
import re as _re
cfg_b = {"enabled": True, "source": "bundled", "path": None, "url": None,
         "inject": "relevant", "local_budget": 6000}
apex_dir = sf_skills.SKILLS_DIR / "platform-apex-generate"
svc = (apex_dir / "assets" / "service.cls").read_text(encoding="utf-8").strip()
ctx_cloud = sf_skills.build_skill_context(APEX, cfg_b)
ctx_cond = sf_skills.build_skill_context(APEX, cfg_b, budget=6000)
labels = _re.findall(r"### Skill file: `([^`]+)`", ctx_cloud)
print(f"INFO bundled Apex context: cloud {len(ctx_cloud)} chars, {len(labels)} linked files; condensed {len(ctx_cond)} chars")
check("bundled Apex cloud context contains the service template text", svc[:200] in ctx_cloud and "`assets/service.cls`" in ctx_cloud)
check("bundled Apex cloud context contains a reference class", "`references/AccountService.cls`" in ctx_cloud)
check("bundled Apex cloud context: all 17 linked files present", len(labels) == 17, str(labels))
check("bundled Apex condensed context has no templates", "Skill file:" not in ctx_cond and svc[:200] not in ctx_cond)
root_s = str(apex_dir.resolve())
inside = all(str((apex_dir / l).resolve()).startswith(root_s + os.sep) for l in labels)
check("bundled Apex linked files are all inside the skill folder", inside and all(".." not in l and not l.startswith("/") for l in labels), str(labels))
check("bundled Apex: no scripts or markdown injected as files", not any(l.endswith((".py", ".sh", ".md")) for l in labels), str(labels))
ctx_soql = sf_skills.build_skill_context(SOQL, cfg_b)
check("bundled SOQL cloud context: no file blocks (links only markdown)", "Skill file:" not in ctx_soql and "platform-soql-query" in ctx_soql)
seen = []
def fake_url(base, rel, use_cache=True):
    seen.append(rel)
    if rel.endswith("SKILL.md"): return (apex_dir / "SKILL.md").read_text(encoding="utf-8")
    if rel.endswith("assets/rest-resource.cls"): return "y" * 40000
    return "// remote " + rel
real_url = sf_skills._load_file_url
sf_skills._load_file_url = fake_url
ctx_http = sf_skills.build_skill_context(APEX, dict(cfg_b, source="url", url="https://mirror.invalid/sf"))
sf_skills._load_file_url = real_url
check("url source: linked assets fetched under platform-apex-generate/", all(r.startswith("platform-apex-generate/") for r in seen) and "// remote platform-apex-generate/assets/service.cls" in ctx_http, str(seen[:4]))
check("url source: over-cap asset skipped", "yyyyyyyy" not in ctx_http and "### Skill file: `assets/rest-resource.cls`" not in ctx_http)

print("\nfailures:", fails)
sys.exit(1 if fails else 0)
