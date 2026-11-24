import sys, os, tempfile, json, time
from types import SimpleNamespace as NS
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp; os.environ["HOME"] = tmp; os.environ["XDG_DATA_HOME"] = tmp
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import openai, ai_client
from ai_client import describe_error, ProviderStreamError, Resolved
try:                       # the HTTP library the openai SDK is built on (httpx2 in current releases)
    import httpx2 as httpx
except ImportError:
    import httpx
# Real request/response objects: newer SDKs read their headers and history when building an error.
_REQ = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
def _resp(status, headers=None): return httpx.Response(status, headers=headers or {}, request=_REQ)

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

def rl(body, headers=None, status=429):
    resp = _resp(status, headers)
    cls = openai.RateLimitError if status == 429 else openai.BadRequestError
    return cls(f"Error code: {status}", response=resp, body=body)

OR = Resolved("https://openrouter.ai/api/v1", "google/gemma-4-26b-a4b-it:free", "SECRETKEY-1234")
ORP = Resolved("https://openrouter.ai/api/v1", "google/gemma-4-26b-a4b-it", "SECRETKEY-1234")
OAI = Resolved("https://api.openai.com/v1", "gpt-5", "SECRETKEY-1234")
ANT = Resolved("https://api.anthropic.com/v1", "claude-sonnet-4-6", "SECRETKEY-1234")

# ---- OpenRouter free model ---------------------------------------------------------------------
body = {"error": {"message": "Provider returned error", "code": 429,
        "metadata": {"provider_name": "Google AI Studio", "raw": "google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream. Please retry shortly."}}}
m = describe_error(rl(body, {"retry-after": "42"}), OR, OR.model)
check("free: names host and model", "Rate limited (429) by openrouter.ai for google/gemma-4-26b-a4b-it:free." in m, m)
check("free: explains the free-tier caps", "20 requests a minute" in m and "1,000 a day" in m, m)
check("free: suggests the paid model by name", "choose google/gemma-4-26b-a4b-it (without ':free')" in m, m)
check("free: uses Retry-After", "about 43 seconds" in m, m)
check("free: shows the provider and its raw reason", 'The provider said (Google AI Studio): "google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream.' in m, m)
check("free: mentions skills as a token lever", "Settings → Skills" in m, m)
check("never contains the API key", "SECRETKEY" not in m, m)
check("paragraphs separated by blank lines (renders in markdown)", m.count("\n\n") >= 3, repr(m))

# ---- OpenRouter paid ------------------------------------------------------------------------------
m = describe_error(rl(body), ORP, ORP.model)
check("paid: providers busy, no 'switch to paid' advice", "Every provider serving this model is busy" in m and "without ':free'" not in m, m)
check("no retry hint -> 'a minute'", "Wait a minute and send again." in m, m)

# ---- billing 429 (OpenAI insufficient_quota) ----------------------------------------------------------
b = {"error": {"message": "You exceeded your current quota, please check your plan and billing details.", "type": "insufficient_quota", "code": "insufficient_quota"}}
m = describe_error(rl(b), OAI, OAI.model)
check("billing 429 is explained as billing, not speed", "about billing, not speed" in m and "faster than your plan" not in m, m)
check("billing 429 says a subscription is not API credit", "does not cover API use" in m, m)
m = describe_error(rl({"error": {"message": "Your quota is exhausted"}}), OAI, OAI.model)
check("openai 'quota' wording without a code is also billing", "about billing" in m, m)

# ---- generic provider ------------------------------------------------------------------------------------
m = describe_error(rl({"error": {"message": "rate_limit_error: too many requests", "type": "rate_limit_error"}}, {"retry-after": "7"}), ANT, ANT.model)
check("generic: plan-speed wording, host and wait", "arriving faster than your plan allows" in m and "api.anthropic.com" in m and "about 8 seconds" in m, m)
check("generic: provider message quoted", 'rate_limit_error: too many requests' in m, m)
m = describe_error(rl("plain string body"), ANT, ANT.model)
check("non-dict body tolerated", "Rate limited (429)" in m, m)
m = describe_error(rl(None), None, None)
check("no resolved connection tolerated", m.startswith("Rate limited (429) by the provider."), m)

# ---- retry hints --------------------------------------------------------------------------------------------
now = time.time()
for hdrs, want in [({"retry-after-ms": "1500"}, "about 2 seconds"),
                   ({"retry-after": "125"}, "about 2 minutes"),
                   ({"retry-after": "7200"}, "about 2 hours"),
                   ({"x-ratelimit-reset": str(int((now + 30) * 1000))}, "seconds"),
                   ({"x-ratelimit-reset": str(int(now + 30))}, "seconds"),
                   ({"retry-after": "abc"}, "a minute"),
                   ({"retry-after": "-5"}, "a minute"),
                   ({"x-ratelimit-reset": str(int((now - 100) * 1000))}, "a minute"),
                   ({}, "a minute")]:
    m = describe_error(rl(body, hdrs), ORP, ORP.model)
    check(f"retry hint {list(hdrs.items())[:1]} -> {want}", f"Wait {want}" in m or (want == "seconds" and "seconds and send again" in m), m.split("\n\n")[2] if m.count("\n\n") > 1 else m)

# ---- other errors are untouched ------------------------------------------------------------------------------
e = rl({"error": {"message": "bad param"}}, status=400)
check("non-429 SDK error keeps its original text", describe_error(e, OR, OR.model) == str(e))
check("plain exception keeps its text", describe_error(RuntimeError("No API key is saved"), OR, "m") == "No API key is saved")

# ---- long provider text is clipped ------------------------------------------------------------------------------
m = describe_error(rl({"error": {"message": "x" * 5000}}), ANT, ANT.model)
check("very long provider message clipped", len(m) < 1200 and "…" in m, str(len(m)))

# ---- the SDK's own mid-stream error: APIError with no status_code (found by the packaged-backend test) -------------
api = openai.APIError("Rate limit exceeded", _REQ, body={"code": 429, "message": "Rate limit exceeded",
                      "metadata": {"provider_name": "Google AI Studio", "raw": "busy"}})
check("test setup: SDK APIError has no status_code", getattr(api, "status_code", None) is None)
m = describe_error(api, OR, OR.model)
check("SDK mid-stream APIError with code 429 gets the friendly message", "Rate limited (429) by openrouter.ai" in m and "paid model" in m and "Google AI Studio" in m, m)
api5 = openai.APIError("upstream exploded", _REQ, body={"code": 500, "message": "upstream exploded"})
m5 = describe_error(api5, OR, OR.model)
check("SDK mid-stream APIError with code 500 is explained as a server error", m5.startswith("The reply from openrouter.ai for google/gemma-4-26b-a4b-it:free stopped with error 500: an internal error on its side.") and 'The provider said: "upstream exploded"' in m5, m5)
api4 = openai.APIError("bad thing", _REQ, body={"code": 400, "message": "bad thing"})
check("SDK APIError with a 4xx code keeps its text", describe_error(api4, OR, OR.model) == "bad thing", describe_error(api4, OR, OR.model))
api_s = openai.APIError("odd", _REQ, body={"code": "insufficient_quota", "message": "You exceeded your current quota"})
check("APIError with a string code is not treated as a status", describe_error(api_s, OAI, OAI.model) == "odd")
api_n = openai.APIError("no body", _REQ, body=None)
check("APIError with no body keeps its text", describe_error(api_n, OR, OR.model) == "no body")

# ---- OpenRouter guardrail 403 ---------------------------------------------------------------------------------------
ORG = Resolved("https://openrouter.ai/api/v1", "anthropic/claude-sonnet-5.5", "SECRETKEY-1234")
ORU = Resolved("https://us.openrouter.ai/api/v1", "anthropic/claude-sonnet-5.5", "SECRETKEY-1234")
region_msg = ("This request arrived on the global data region, but the key's workspace permits requests only on these "
              "OpenRouter hostnames: us.openrouter.ai. Use one of the permitted hostnames or update the workspace guardrail allowed data regions.")
m = describe_error(rl({"error": {"message": region_msg, "code": 403}}, status=403), ORG, ORG.model)
check("403 region: says the guardrail only accepts US and Avio used Global",
      "only accepts requests through US" in m and "Global address (openrouter.ai)" in m, m)
check("403 region: offers both fixes (Avio region, or the guardrail)", "set this connection's OpenRouter region to US" in m and "add Global under Data regions" in m, m)
check("403 region: names where the guardrail lives", "Workspaces → Default → Guardrails" in m, m)
check("403 region: quotes OpenRouter's own message", 'OpenRouter said: "This request arrived on the global data region' in m, m)
m2 = describe_error(rl({"error": {"message": region_msg.replace("us.openrouter.ai", "eu.openrouter.ai, us.openrouter.ai"), "code": 403}}, status=403), ORG, ORG.model)
check("403 region: several allowed regions are listed", "through EU or US" in m2 and "region to EU or US" in m2, m2)
m3 = describe_error(rl({"error": {"message": "Request arrived on us region but only global is permitted: data region guardrail", "code": 403}}, status=403), ORU, ORU.model)
check("403 data-region wording without a hostname list still explains", "OpenRouter refused this request (403)" in m3 and "US address (us.openrouter.ai)" in m3, m3)
plan_msg = ("Regional routing requires a Business or Enterprise plan. Upgrade at https://openrouter.ai/settings/manage-plan, "
            "then send requests to eu.openrouter.ai or us.openrouter.ai.")
pm = describe_error(rl({"error": {"message": plan_msg, "code": 403}}, status=403), ORU, "qwen/qwen3-coder")
check("403 plan: says the PLAN is the cause, for the US address", "plan doesn't include US routing" in pm and "Business or Enterprise" in pm, pm)
check("403 plan: says it is about the account, not the model", "about your account, not the model you chose" in pm, pm)
check("403 plan: does NOT claim a guardrail allowlist problem", "almost always an account guardrail" not in pm and "allow this model" not in pm, pm)
check("403 plan: tells the user what to do (Global, and the guardrail's Data regions)",
      "set this connection's region to Global" in pm and "allow Global there too" in pm and "Data regions" in pm, pm)
check("403 plan: is honest about what Global cannot promise", "can't promise" in pm and "processed in one region" in pm, pm)
check("403 plan: quotes OpenRouter's own message and names the upgrade page", 'OpenRouter said: "Regional routing requires a Business or Enterprise plan' in pm and "manage-plan" in pm, pm)
check("403 plan: names the model it was sent for", "for qwen/qwen3-coder" in pm, pm)
check("403 plan on the EU address names EU", "plan doesn't include EU routing" in describe_error(rl({"error": {"message": plan_msg, "code": 403}}, status=403), Resolved("https://eu.openrouter.ai/api/v1", "m", "k"), "m"))
check("403 plan reported mid-stream is explained the same way", "plan doesn't include US routing" in describe_error(openai.APIError("blocked", _REQ, body={"code": 403, "message": plan_msg}), ORU, ORU.model))
other = describe_error(rl({"error": {"message": "Model anthropic/claude-x is not allowed by your guardrail", "code": 403}}, status=403), ORU, ORU.model)
check("403 model/provider/budget: points at the guardrail and Avio's region", "almost always an account guardrail" in other and "match Avio's settings" in other and "include the US region" in other, other)
check("403: never contains the key", "SECRETKEY" not in m and "SECRETKEY" not in other)
plain = rl({"error": {"message": "forbidden"}}, status=403)
check("403 from a non-OpenRouter host keeps its original text", describe_error(plain, OAI, OAI.model) == str(plain))
check("403 with no connection keeps its original text", describe_error(plain, None, None) == str(plain))
sdk403 = openai.APIError("blocked", _REQ, body={"code": 403, "message": region_msg})
check("403 reported mid-stream (SDK APIError) is explained too", "only accepts requests through US" in describe_error(sdk403, ORG, ORG.model), describe_error(sdk403, ORG, ORG.model))
check("429 behaviour is unchanged", "Rate limited (429)" in describe_error(rl(body), ORG, ORG.model))

# ---- ProviderStreamError ----------------------------------------------------------------------------------------
m = describe_error(ProviderStreamError(429, "Rate limit exceeded", "Google AI Studio", "capacity"), OR, OR.model)
check("mid-stream 429 gets the same explanation", "Rate limited (429)" in m and "paid model" in m and "capacity" in m, m)
m = describe_error(ProviderStreamError(400, "context too long"), OR, OR.model)
check("mid-stream non-429 is reported, not swallowed", m == "The provider stopped the reply with an error (code 400): context too long", m)
m = describe_error(ProviderStreamError(), OR, OR.model)
check("mid-stream error with no detail still says so", m.startswith("The provider stopped the reply with an error"), m)
check("string status is parsed", ProviderStreamError("429", "x").status == 429)

# ---- the stream raises instead of finishing quietly ------------------------------------------------------------------
class Stream:
    def __init__(self, chunks): self.chunks = chunks
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __iter__(self): return iter(self.chunks)
def chunk(content=None, finish=None, extra=None):
    return NS(choices=[NS(delta=NS(content=content), finish_reason=finish)], model_extra=extra or {})
def run(chunks):
    ai = ai_client.AIClient(); ai._create = lambda *a, **k: Stream(chunks)
    return list(ai.stream([{"role": "user", "content": "q"}], system="S", model="m", resolved=OR))

out = run([chunk("Hel"), chunk("lo"), chunk(None, "stop")])
check("normal stream unchanged", out[:2] == ["Hel", "lo"] and out[-1].reason == "stop", str(out))
for name, chunks, status in [
    ("error object in a chunk", [chunk("par"), chunk(None, None, {"error": {"code": 429, "message": "Rate limit exceeded", "metadata": {"provider_name": "P", "raw": "slow down"}}})], 429),
    ("finish_reason 'error' with no detail", [chunk("par"), chunk("", "error")], None),
]:
    try:
        run(chunks); check(f"stream: {name} raises", False, "no exception")
    except ProviderStreamError as e:
        check(f"stream: {name} raises ProviderStreamError", e.status == status, f"status={e.status}")
try:
    run([chunk("x", None, {"error": "plain string error"})]); check("stream: string error raises", False, "no exception")
except ProviderStreamError as e:
    check("stream: string error raises with its text", "plain string error" in str(e))
class OldStyle:      # a chunk object with no model_extra at all (older SDK / test fakes)
    choices = [NS(delta=NS(content="ok"), finish_reason="stop")]
out = run([OldStyle()])
check("chunks without model_extra still work", out[0] == "ok", str(out))

# ---- server errors (5xx): the provider's failure, said plainly ---------------------------------------------------------
def se(status, body, headers=None, text=None):
    resp = _resp(status, headers)
    return openai.InternalServerError(text or f"Error code: {status}", response=resp, body=body)
ORN = Resolved("https://us.openrouter.ai/api/v1", "nvidia/nemotron-3-ultra-550b-a55b", "SECRETKEY-1234")
LOC = Resolved("http://localhost:11434/v1", "llama3:8b", "")
CF522 = ("<!DOCTYPE html>\n<html lang=\"en-US\"><head>\n<title>us.openrouter.ai | 522: Connection timed out</title>\n<meta charset=\"UTF-8\" />"
         "</head><body><div id=\"cf-wrapper\"><h1>Connection timed out</h1><p>" + "filler " * 400 + "</p></div></body></html>")
m = describe_error(se(522, CF522, text=CF522), ORN, ORN.model)
paras = m.split("\n\n")
check("522: first line names the host, the model, the code and what it means",
      paras[0] == "us.openrouter.ai could not answer for nvidia/nemotron-3-ultra-550b-a55b: error 522, a connection timeout (the server behind it could not be reached in time).", paras[0])
check("522: says it is the provider's side, not the key or settings, and that Avio retried",
      paras[1] == "This is a problem on the provider's side, not your API key or Avio's settings. Avio already tried again once.", paras[1])
check("522: OpenRouter advice (send again, another model, a second provider in the guardrail)",
      paras[2].startswith("Send the message again in a moment.") and "pick another model" in paras[2] and "allow a second provider" in paras[2] and "no fallback" in paras[2], paras[2])
check("522: the HTML error page is reduced to its title", paras[3] == 'The provider said: "us.openrouter.ai | 522: Connection timed out"', paras[3:])
check("522: no HTML and no filler in the message", "<" not in m and "filler" not in m and len(m) < 900, str(len(m)))
check("522: never contains the API key", "SECRETKEY" not in m)
check("522: four paragraphs separated by blank lines", len(paras) == 4, repr(m))
m = describe_error(se(522, None), ORN, ORN.model)
check("a bare 'Error code: 522' is not quoted back", "The provider said" not in m and m.count("\n\n") == 2, m)
m = describe_error(se(522, "<html><body>no title here</body></html>", text="<html><body>no title here</body></html>"), ORN, ORN.model)
check("an HTML page without a title is dropped", "The provider said" not in m and "<" not in m, m)

b503 = {"error": {"code": 503, "message": "No endpoints found matching your data policy", "metadata": {"error_type": "provider_overloaded"}}}
m = describe_error(se(503, b503, {"retry-after": "30"}), ORN, ORN.model)
check("OpenRouter 503: no host available, in OpenRouter's meaning", "error 503, no host is available for this model right now." in m, m)
check("OpenRouter 503: uses Retry-After", "Wait about 31 seconds and send again." in m, m)
check("OpenRouter 503: quotes OpenRouter's message", 'The provider said: "No endpoints found matching your data policy"' in m, m)
b502 = {"error": {"code": 502, "message": "Provider returned error", "metadata": {"provider_name": "DeepInfra", "raw": "upstream connect error or disconnect/reset before headers"}}}
m = describe_error(se(502, b502), ORN, ORN.model)
check("OpenRouter 502: the model's host is down or answered badly", "error 502, the model's host is down or returned an invalid response." in m, m)
check("OpenRouter 502: names the host that failed and its raw reason", 'The provider said (DeepInfra): "upstream connect error or disconnect/reset before headers"' in m, m)

m = describe_error(ProviderStreamError(502, "Provider disconnected mid-stream", "DeepInfra", ""), ORN, ORN.model)
check("mid-stream 502: says the reply stopped, with the meaning",
      m.startswith("The reply from us.openrouter.ai for nvidia/nemotron-3-ultra-550b-a55b stopped with error 502: the model's host is down or returned an invalid response."), m)
check("mid-stream 502: does not claim a retry (a started reply is not retried)", "tried again" not in m and "not your API key" in m, m)
check("mid-stream 502: quotes the provider", 'The provider said (DeepInfra): "Provider disconnected mid-stream"' in m, m)
m = describe_error(openai.APIError("gateway", _REQ, body={"code": 522, "message": "gateway"}), ORN, ORN.model)
check("SDK mid-stream APIError with code 522 uses the mid-stream wording", m.startswith("The reply from us.openrouter.ai") and "error 522: a connection timeout" in m and "tried again" not in m, m)

m = describe_error(se(529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}), ANT, ANT.model)
check("Anthropic 529: overloaded, with the general advice", "api.anthropic.com could not answer for claude-sonnet-4-6: error 529, the provider is overloaded." in m
      and "check the provider's status page or use another connection" in m and "guardrail" not in m, m)
check("Anthropic 529: quotes its message", 'The provider said: "Overloaded"' in m, m)
m = describe_error(se(500, {"error": {"message": "model runner has unexpectedly stopped"}}), LOC, LOC.model)
check("local 500: points at the local model server, not at a status page",
      "localhost could not answer for llama3:8b: error 500, an internal error on its side." in m and "local model server is still running" in m and "status page" not in m, m)
m = describe_error(se(599, None), OAI, OAI.model)
check("an unlisted 5xx still gets the explanation", "error 599, a server error." in m and "provider's side" in m, m)
m = describe_error(se(503, None), None, None)
check("no resolved connection tolerated", m.startswith("the provider could not answer: error 503, service unavailable."), m)
m = describe_error(se(502, {"error": {"message": "bad gateway", "code": 502}}), OAI, OAI.model)
check("the OpenRouter meanings are not used for other providers", "a bad gateway (the server behind it gave no valid answer)" in m, m)
m = describe_error(se(503, {"error": {"message": "y" * 5000}}), OAI, OAI.model)
check("a very long provider message is clipped", len(m) < 900, str(len(m)))
e404 = openai.NotFoundError("Error code: 404 - no such model", response=_resp(404), body={"error": {"message": "no such model"}})
check("a 404 keeps its original text", describe_error(e404, ORN, ORN.model) == str(e404))

# ---- server errors over real HTTP: what the SDK really raises, and how often it asks ------------------------------------
import http.server, threading, socket
hits = {}
class SrvErr(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); req = json.loads(self.rfile.read(n) or b"{}")
        model = req.get("model", ""); hits[model] = hits.get(model, 0) + 1
        if model == "cf522":
            body = CF522.encode(); self.send_response(522); self.send_header("Content-Type", "text/html; charset=UTF-8")
        elif model == "or503":
            body = json.dumps(b503).encode(); self.send_response(503); self.send_header("Content-Type", "application/json"); self.send_header("Retry-After", "1")
        elif model == "flaky":          # fails once, then answers: the retry must make it work
            if hits[model] == 1:
                body = b"{}"; self.send_response(502); self.send_header("Content-Type", "application/json")
            else:
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                base = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": model}
                for o in ({**base, "choices": [{"index": 0, "delta": {"content": "recovered"}, "finish_reason": "stop"}]},):
                    self.wfile.write(b"data: " + json.dumps(o).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush(); return
        else:                            # "mid502": an error event after the stream has started
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            base = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": model}
            for o in ({**base, "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}]},
                      {**base, "error": {"code": 502, "message": "Provider disconnected mid-stream", "metadata": {"provider_name": "FakeHost"}},
                       "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "error"}]}):
                self.wfile.write(b"data: " + json.dumps(o).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush(); return
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
# The fake must look like a cloud provider. 127.0.0.2 is loopback but not treated as local (ai_client._LOOPBACK);
# Windows and Linux route it, macOS does not unless aliased. There, use 127.0.0.1 and mark just this URL as cloud.
def _bindable(host):
    try:
        with socket.socket() as t: t.bind((host, 0))
        return True
    except OSError:
        return False
CLOUD = "127.0.0.2" if _bindable("127.0.0.2") else "127.0.0.1"
s = socket.socket(); s.bind((CLOUD, 0)); PORT5 = s.getsockname()[1]; s.close()
srv5 = http.server.ThreadingHTTPServer((CLOUD, PORT5), SrvErr)
threading.Thread(target=srv5.serve_forever, daemon=True).start()
CLOUD_URL = f"http://{CLOUD}:{PORT5}/v1"
real_is_local = ai_client._is_local
if CLOUD == "127.0.0.1":
    ai_client._is_local = lambda url: False if (url or "").startswith(CLOUD_URL) else real_is_local(url)
real = ai_client.AIClient()
def ask(model):
    r = Resolved(CLOUD_URL, model, "SECRETKEY-1234")     # a cloud stand-in, not a local server
    out = []
    try:
        for x in real.stream([{"role": "user", "content": "q"}], system="S", model=model, resolved=r):
            out.append(x)
        return out, None, r
    except Exception as e:
        return out, e, r
out, e, r = ask("cf522")
check("real 522: the SDK raises a status error with status_code 522", getattr(e, "status_code", None) == 522, repr(e)[:200])
check("real 522: Avio asked twice (one retry), as the message says", hits.get("cf522") == 2 and ai_client.CHAT_MAX_RETRIES == 1, str(hits))
m = describe_error(e, r, "cf522")
check("real 522: friendly message, HTML reduced to its title, nothing else leaked",
      m.startswith(f"{CLOUD} could not answer for cf522: error 522, a connection timeout") and "Avio already tried again once." in m
      and 'The provider said: "us.openrouter.ai | 522: Connection timed out"' in m and "<" not in m and "filler" not in m and "SECRETKEY" not in m, m)
check("real 522: before this change the panel showed only the SDK's bare text", str(e) == "Error code: 522" and isinstance(e.body, str) and "<html" in e.body, repr(str(e)))
out, e, r = ask("or503")
m = describe_error(e, r, "or503")
check("real 503 with a JSON body: status, retry count and OpenRouter's message", getattr(e, "status_code", None) == 503 and hits.get("or503") == 2
      and "error 503, service unavailable." in m and 'The provider said: "No endpoints found matching your data policy"' in m, m)
out, e, r = ask("flaky")
check("a server error that clears on the retry is not shown at all", e is None and out[:1] == ["recovered"] and hits.get("flaky") == 2, f"{out!r} {e!r} {hits}")
out, e, r = ask("mid502")
m = describe_error(e, r, "mid502") if e else ""
check("real mid-stream 502: the partial text arrived, then the error is explained without a retry claim",
      out[:1] == ["partial"] and isinstance(e, openai.APIError) and getattr(e, "status_code", None) is None and hits.get("mid502") == 1
      and m.startswith(f"The reply from {CLOUD} for mid502 stopped with error 502: a bad gateway") and "tried again" not in m and 'The provider said (FakeHost): "Provider disconnected mid-stream"' in m, f"{out!r} | {m}")
srv5.shutdown(); ai_client._is_local = real_is_local

# ---- endpoint end to end -----------------------------------------------------------------------------------------------------
from fastapi.testclient import TestClient
import main
main.connections.resolve = lambda cid=None: OR
main.augment_with_skills = lambda system, messages, force=None, local=False: (system or "", [])
tc = TestClient(main.app)
def events(path="/api/ai/chat"):
    r = tc.post(path, json={"messages": [{"role": "user", "content": "hi"}], "system": "S"})
    return [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ") and l[6:] != "[DONE]"]
def raises(e):
    def f(messages, system=None, model=None, resolved=None, request_id=None):
        raise e
        yield
    return f
main._ai.stream = raises(rl(body, {"retry-after": "30"}))
ev = events()
err = [x for x in ev if "error" in x]
check("endpoint: 429 becomes the friendly message", err and "Rate limited (429) by openrouter.ai" in err[0]["error"] and "paid model" in err[0]["error"], str(ev))
check("endpoint: skills event still comes first", "skills" in ev[0], str(ev))
check("endpoint: key not leaked", "SECRETKEY" not in json.dumps(ev))
main._ai.stream = raises(RuntimeError("some other failure"))
check("endpoint: other errors unchanged", [x for x in events("/api/claude/chat") if "error" in x][0]["error"] == "some other failure")
def midstream(messages, system=None, model=None, resolved=None, request_id=None):
    yield "partial"; raise ProviderStreamError(429, "Rate limit exceeded")
main._ai.stream = midstream
ev = events()
check("endpoint: delta then friendly error for a mid-stream limit", any(x.get("delta") == "partial" for x in ev) and any("Rate limited (429)" in x.get("error", "") for x in ev), str(ev))

print("\nfailures:", fails)
sys.exit(1 if fails else 0)
