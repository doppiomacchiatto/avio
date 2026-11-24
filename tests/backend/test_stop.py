import sys, os, tempfile, json, time, threading, http.server
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp; os.environ["HOME"] = tmp; os.environ["XDG_DATA_HOME"] = tmp
os.environ["AVIO_API_TOKEN"] = "test-token"
os.environ["AVIO_SECRET_BACKEND"] = "file"   # the "Fake"/"Slow" connection keys stay in tmp, never in Credential Manager
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import ai_client
from ai_client import Resolved, AIClient, describe_error

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

# ---- a fake provider that can stream, stall and notice when the client hangs up ----------------------------
STATE = {"closed": [], "opened": []}
PORT = 7889
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); req = json.loads(self.rfile.read(n) or b"{}")
        model = req.get("model", ""); STATE["opened"].append(model)
        if model == "hang":                       # accepts the request, never answers
            time.sleep(8); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        base = {"id": "c1", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
        def send(obj): self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n"); self.wfile.flush()
        try:
            if model == "silent":                 # headers sent, then nothing at all
                time.sleep(8); return
            send({**base, "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}]})
            if model == "ok":
                send({**base, "choices": [{"index": 0, "delta": {"content": " done"}, "finish_reason": "stop"}]})
                self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush(); return
            # "slow": keep the connection open and keep sending until the client goes away
            for _ in range(80):
                time.sleep(0.1)
                send({**base, "choices": [{"index": 0, "delta": {"content": "."}, "finish_reason": None}]})
        except (BrokenPipeError, ConnectionResetError, OSError):
            STATE["closed"].append(model)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
R = lambda model: Resolved(f"http://127.0.0.1:{PORT}/v1", model, "k")
M = [{"role": "user", "content": "q"}]

# ---- timeout setting --------------------------------------------------------------------------------------------
cfg = {}
ai_client._load_avio_config = lambda: cfg
check("default timeout: cloud 300s", ai_client._load_chat_timeout("https://api.openai.com/v1") == 300)
check("default timeout: local 900s", ai_client._load_chat_timeout("http://localhost:11434/v1") == 900 and ai_client._load_chat_timeout("http://127.0.0.1:1/v1") == 900)
cfg["chat_timeout_seconds"] = 120
check("config.json overrides it", ai_client._load_chat_timeout("https://api.openai.com/v1") == 120 and ai_client._load_chat_timeout("http://localhost/v1") == 120)
for bad in (5, 9, 3601, 100000, "abc", None, -1, 0, [], {}):
    cfg["chat_timeout_seconds"] = bad
    check(f"out-of-range or junk {bad!r} falls back to the default", ai_client._load_chat_timeout("https://x.example/v1") == 300, str(ai_client._load_chat_timeout("https://x.example/v1")))
cfg["chat_timeout_seconds"] = "45"
check("a numeric string works", ai_client._load_chat_timeout("https://x.example/v1") == 45)
cfg.clear()

ai = AIClient()
c = ai._client_for(Resolved("https://api.openai.com/v1", "m", "k"))
check("chat client: read timeout 300s, connect 15s", c.timeout.read == 300 and c.timeout.connect == 15, str(c.timeout))
check("chat client: one retry, not two", c.max_retries == 1, str(c.max_retries))
c2 = ai._client_for(Resolved("http://localhost:11434/v1", "m", "k"))
check("local client: read timeout 900s", c2.timeout.read == 900, str(c2.timeout))
cfg["chat_timeout_seconds"] = 60
c3 = ai._client_for(Resolved("https://api.openai.com/v1", "m", "k"))
check("a changed timeout builds a new client (cache key includes it)", c3 is not c and c3.timeout.read == 60)
cfg.clear()
check("same settings reuse the client", ai._client_for(Resolved("https://api.openai.com/v1", "m", "k")) is c)

# ---- describe_error for timeouts -------------------------------------------------------------------------------
import openai
try:
    import httpx
except ImportError:
    import httpx2 as httpx
try:
    import httpx2
except Exception:
    httpx2 = None
req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
t1 = openai.APITimeoutError(request=req)
m = describe_error(t1, Resolved("https://api.example.com/v1", "grok-x", "k"), "grok-x")
check("SDK timeout -> plain message naming host, model, and the wait", "No reply from api.example.com for grok-x in 5 minutes" in m and "stopped waiting" in m, m)
check("it mentions overload/reasoning and the setting to change", "thinking for a very long time" in m and "chat_timeout_seconds" in m)
check("no raw 'Request timed out.' only", m != "Request timed out.")
mo = describe_error(t1, Resolved("https://us.openrouter.ai/api/v1", "x-ai/grok-4.7", "k"), "x-ai/grok-4.7")
check("OpenRouter: suggests a model with more than one host in your region", "more than one host serves in your region" in mo, mo)
ml = describe_error(t1, Resolved("http://localhost:11434/v1", "llama3", "k"), "llama3")
check("local: says the model may still be loading, in 15 minutes", "15 minutes" in ml and "still be loading" in ml and "thinking" not in ml, ml)
cfg["chat_timeout_seconds"] = 90
check("custom wait is shown in seconds when not a whole number of minutes >= 2", "in 90 seconds" in describe_error(t1, Resolved("https://a.example/v1", "m", "k"), "m"))
cfg.clear()
for exc in (httpx.ReadTimeout("x"), httpx.ConnectTimeout("x"), httpx.PoolTimeout("x")):
    check(f"raw {type(exc).__name__} (surfaces mid-stream) is also explained", "stopped waiting" in describe_error(exc, Resolved("https://a.example/v1", "m", "k"), "m"))
if httpx2:
    check("raw httpx2.ReadTimeout is also explained", "stopped waiting" in describe_error(httpx2.ReadTimeout("x"), Resolved("https://a.example/v1", "m", "k"), "m"))
check("a non-timeout error keeps its own text", describe_error(RuntimeError("boom"), Resolved("https://a.example/v1", "m", "k"), "m") == "boom")
check("a 429 is still explained as before", "Rate limited (429)" in describe_error(
    openai.RateLimitError("x", response=httpx.Response(429, request=req, json={"error": {"message": "slow"}}), body={"error": {"message": "slow"}}),
    Resolved("https://a.example/v1", "m", "k"), "m"))

# ---- a real stall times out (timeout shortened for the test) ---------------------------------------------------
orig = ai_client._load_chat_timeout
ai_client._load_chat_timeout = lambda url: 1
ai2 = AIClient()
t0 = time.time()
got, err = [], None
try:
    for ch in ai2.stream(M, resolved=R("silent")): got.append(ch)
except Exception as e:
    err = e
dt = time.time() - t0
check("silent host: gives up after about the timeout, not minutes", err is not None and dt < 6, f"{dt:.1f}s {err!r}")
check("silent host: the error is recognised as a timeout and explained", err is not None and ai_client._is_timeout(err) and "stopped waiting" in describe_error(err, R("silent"), "silent"), repr(err))
t0 = time.time(); err = None
try:
    for ch in ai2.stream(M, resolved=R("hang")): pass
except Exception as e:
    err = e
dt = time.time() - t0
check("host that never answers: times out (one retry, so about 2 waits)", err is not None and dt < 7 and ai_client._is_timeout(err), f"{dt:.1f}s {err!r}")
ai_client._load_chat_timeout = orig

# ---- normal replies are unchanged ----------------------------------------------------------------------------
ai = AIClient()
out = list(ai.stream(M, resolved=R("ok"), request_id="req-normal-1"))
check("normal reply: text then StreamFinish", [x for x in out if isinstance(x, str)] == ["partial", " done"] and isinstance(out[-1], ai_client.StreamFinish) and out[-1].reason == "stop", repr(out))
check("normal reply: nothing left registered", not ai._live and "req-normal-1" not in ai._cancelled)
out = list(ai.stream(M, resolved=R("ok")))
check("a reply without a request id still works", len(out) == 3)

# ---- Stop ---------------------------------------------------------------------------------------------------
def run_slow(rid, results, stop_after=None):
    try:
        for ch in ai.stream(M, resolved=R("slow"), request_id=rid):
            results.append(ch)
    except Exception as e:
        results.append(e)
res = []
STATE["closed"].clear()
th = threading.Thread(target=run_slow, args=("req-stop-1", res)); th.start()
t0 = time.time()
while not res and time.time() - t0 < 5: time.sleep(0.05)
check("slow reply is streaming", res and res[0] == "partial", repr(res))
n_before = len(res)
t1 = time.time()
stopped = ai.cancel("req-stop-1")
th.join(5)
check("cancel reports it closed a live stream", stopped is True)
check("the stream ends promptly after cancel", not th.is_alive() and time.time() - t1 < 3, f"{time.time()-t1:.1f}s")
check("no exception and no StreamFinish after a cancel", not any(isinstance(x, (Exception, ai_client.StreamFinish)) for x in res), repr(res[-3:]))
check("what arrived before Stop is kept", res[0] == "partial" and len(res) >= n_before)
time.sleep(0.5)
check("the provider saw the connection close (it stops generating)", "slow" in STATE["closed"], str(STATE))
check("cancelled request is forgotten", "req-stop-1" not in ai._live and "req-stop-1" not in ai._cancelled)

# cancel before the stream opens
opened_before = len(STATE["opened"])
ai.cancel("req-early-1")
list_out = list(ai.stream(M, resolved=R("slow"), request_id="req-early-1"))
check("cancel that arrives first: the request never goes out", list_out == [] and len(STATE["opened"]) == opened_before, str(STATE["opened"][-3:]))
check("...and its id is cleaned up", "req-early-1" not in ai._cancelled)

# cancel of an unknown or finished id
check("cancelling an unknown id is harmless", ai.cancel("req-unknown-1") is False)
for i in range(300): ai.cancel(f"req-junk-{i:04d}")
check("remembered cancelled ids are bounded", len(ai._cancelled) <= 201, str(len(ai._cancelled)))

# a real error is NOT swallowed just because some other request was cancelled
ai._cancelled.clear()
class Boom:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): raise RuntimeError("provider exploded")
    def close(self): pass
ai._create = lambda *a, **k: Boom()
try:
    list(ai.stream(M, resolved=R("x"), request_id="req-err-0001")); e = None
except RuntimeError as ex:
    e = ex
check("a genuine error on an un-cancelled request still raises", e is not None and "exploded" in str(e))
ai.cancel("req-other-0001")
try:
    list(ai.stream(M, resolved=R("x"), request_id="req-err-0002")); e = None
except RuntimeError as ex:
    e = ex
check("...even when a different request was cancelled", e is not None)

# ---- HTTP endpoints ---------------------------------------------------------------------------------------------
import main, connections
from fastapi.testclient import TestClient
H_ = {"Authorization": "Bearer test-token"}
main._ai = AIClient()
with TestClient(main.app) as tc:
    conn = connections.upsert(conn_id=None, label="Fake", preset="custom", base_url=f"http://127.0.0.1:{PORT}/v1", model="ok",
                              api_key="k", clear_key=False, make_default=True)
    body = {"messages": M, "system": "S", "connection": conn["id"], "request_id": "req-http-0001"}
    r = tc.post("/api/ai/chat", headers=H_, json=body)
    events = [json.loads(l[6:]) for l in r.text.split("\n") if l.startswith("data: ") and "[DONE]" not in l]
    check("chat with a request id works over HTTP", "".join(e.get("delta", "") for e in events) == "partial done", r.text[:200])
    check("chat/cancel needs the token", tc.post("/api/ai/chat/cancel", json={"request_id": "req-http-0001"}).status_code == 401)
    r = tc.post("/api/ai/chat/cancel", headers=H_, json={"request_id": "req-http-0001"})
    check("cancel over HTTP answers ok (nothing live)", r.status_code == 200 and r.json() == {"ok": True, "stopped": False}, r.text)
    for bad in ("", "x", "../../etc/passwd", "a b c d e f g h", "x" * 200, "id\n12345678"):
        check(f"cancel rejects bad id {bad[:20]!r}", tc.post("/api/ai/chat/cancel", headers=H_, json={"request_id": bad}).status_code == 400)
    check("cancel without a body is a 422", tc.post("/api/ai/chat/cancel", headers=H_, json={}).status_code == 422)
    # a junk request id on chat is ignored, not an error
    body2 = {**body, "request_id": "bad id!"}
    r = tc.post("/api/ai/chat", headers=H_, json=body2)
    check("chat with a malformed request id still answers (id ignored)", "partial" in r.text)
    # old clients send no id at all
    body3 = {k: v for k, v in body.items() if k != "request_id"}
    check("chat without a request id (older UI) still works", "partial" in tc.post("/api/claude/chat", headers=H_, json=body3).text)
    # Stop through HTTP while a real slow reply streams
    conn2 = connections.upsert(conn_id=None, label="Slow", preset="custom", base_url=f"http://127.0.0.1:{PORT}/v1", model="slow",
                               api_key="k", clear_key=False, make_default=False)
    out = {}
    def go():
        out["r"] = tc.post("/api/ai/chat", headers=H_, json={"messages": M, "connection": conn2["id"], "request_id": "req-http-slow1"})
    th = threading.Thread(target=go); th.start()
    t0 = time.time()
    while "req-http-slow1" not in main._ai._live and time.time() - t0 < 6: time.sleep(0.05)
    check("slow reply is live in the backend", "req-http-slow1" in main._ai._live)
    r = tc.post("/api/ai/chat/cancel", headers=H_, json={"request_id": "req-http-slow1"})
    check("cancel over HTTP closes it", r.status_code == 200 and r.json()["stopped"] is True, r.text)
    th.join(8)
    check("the chat request then ends", not th.is_alive())
    txt = out["r"].text if "r" in out else ""
    check("it ended with [DONE], not an error", "[DONE]" in txt and '"error"' not in txt, txt[-200:])
    time.sleep(0.4)
    check("nothing left registered", not main._ai._live)

srv.shutdown()
print(f"\n{'ALL PASSED' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
