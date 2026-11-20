import sys, os, tempfile, json, time, subprocess
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp; os.environ["HOME"] = tmp; os.environ["XDG_DATA_HOME"] = tmp
HERE = tmp                                        # the stub writes its mode/args/pid files here
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures")
os.environ["STUB_SF_DIR"] = HERE                  # read by fixtures/stub_sf.py
os.environ["AVIO_TEST_PYTHON"] = sys.executable   # used by fixtures/stub_sf.cmd
REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
import sf_cli, org_login

fails = 0
def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))
    if not ok: fails += 1

def mode(m): open(os.path.join(HERE, "stub_mode.txt"), "w").write(m)
def args(): return json.load(open(os.path.join(HERE, "stub_args.txt")))
def wait_state(want, secs=20):
    t = time.time()
    while time.time() - t < secs:
        s = org_login.status()
        if s["state"] in want: return s
        time.sleep(0.2)
    return org_login.status()
def alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out

sf_cli.SF_CLI = os.path.abspath(os.path.join(FIXTURES, "stub_sf.cmd"))

# ---- options and the airgap override ------------------------------------------------------------
cfg = {}
org_login._load_avio_config = lambda: cfg
o = {x["type"]: x for x in org_login.login_options()}
check("defaults: production", o["production"]["url"] == "https://login.salesforce.com" and o["production"]["alias"] == "avio-prod" and not o["production"]["custom"], str(o))
check("defaults: test", o["test"]["url"] == "https://test.salesforce.com" and o["test"]["alias"] == "avio-dev", str(o))
cfg["org_login_urls"] = {"production": "https://login.corp.example/", "test": "https://test.corp.example"}
o = {x["type"]: x for x in org_login.login_options()}
check("config overrides both URLs (trailing slash trimmed)", o["production"]["url"] == "https://login.corp.example" and o["test"]["url"] == "https://test.corp.example" and o["production"]["custom"], str(o))
cfg["org_login_urls"] = {"production": "http://insecure.example", "test": "not a url"}
o = {x["type"]: x for x in org_login.login_options()}
check("http and junk overrides are refused -> defaults", o["production"]["url"] == "https://login.salesforce.com" and o["test"]["url"] == "https://test.salesforce.com" and not o["test"]["custom"], str(o))
cfg["org_login_urls"] = {"production": "--evil https://x", "test": 5}
o = {x["type"]: x for x in org_login.login_options()}
check("option-injection style and non-string overrides refused", o["production"]["url"] == "https://login.salesforce.com" and o["test"]["url"] == "https://test.salesforce.com", str(o))
cfg["org_login_urls"] = "garbage"
check("non-object config tolerated", len(org_login.login_options()) == 2)
cfg.clear()
check("command text", org_login.command_text("test") == "sf org login web --instance-url https://test.salesforce.com --alias avio-dev")
try:
    org_login.start("evil"); check("unknown type rejected", False, "no error")
except ValueError:
    check("unknown type rejected", True)

# ---- success --------------------------------------------------------------------------------------
mode("success")
s = org_login.start("production")
check("start returns running with alias and url", s["state"] == "running" and s["alias"] == "avio-prod" and s["url"] == "https://login.salesforce.com", str(s))
s = wait_state({"success", "error"})
check("success state with username", s["state"] == "success" and s["username"] == "me@example.com", str(s))
check("status never carries tokens", "SECRET" not in json.dumps(s), str(s))
a = args()
check("CLI args: org login web --instance-url <prod> --alias avio-prod --json",
      a == ["org", "login", "web", "--instance-url", "https://login.salesforce.com", "--alias", "avio-prod", "--json"], str(a))

mode("success")
org_login.start("test"); wait_state({"success", "error"})
a = args()
check("test type -> test.salesforce.com and avio-dev", a[4] == "https://test.salesforce.com" and a[6] == "avio-dev", str(a))
cfg["org_login_urls"] = {"test": "https://test.corp.example"}
org_login.start("test"); wait_state({"success", "error"})
check("airgap URL from config reaches the CLI", args()[4] == "https://test.corp.example", str(args()))
cfg.clear()

# ---- failures -----------------------------------------------------------------------------------
mode("fail"); org_login.start("production"); s = wait_state({"success", "error"})
check("CLI JSON error surfaces its message", s["state"] == "error" and "user denied access" in s["message"], str(s))
mode("plainerr"); org_login.start("production"); s = wait_state({"success", "error"})
check("non-JSON failure surfaces stderr", s["state"] == "error" and "port 1717" in s["message"], str(s))

# ---- one at a time, cancel, timeout ---------------------------------------------------------------
mode("hang")
org_login.start("production"); time.sleep(1.5)
pid = int(open(os.path.join(HERE, "stub_pid.txt")).read())
check("hanging login reports running with elapsed", org_login.status()["state"] == "running" and "elapsed" in org_login.status())
try:
    org_login.start("test"); check("second login while one runs is refused", False, "no error")
except RuntimeError:
    check("second login while one runs is refused", True)
check("stub python process is alive before cancel", alive(pid))
s = org_login.cancel()
check("cancel -> cancelled", s["state"] == "cancelled", str(s))
time.sleep(1.5)
check("cancel kills the whole process tree (python child gone)", not alive(pid))
check("state stays cancelled (not overwritten by the dead process)", org_login.status()["state"] == "cancelled")
mode("success")
org_login.start("production"); check("can start again after cancel", wait_state({"success", "error"})["state"] == "success")

mode("hang"); org_login.LOGIN_TIMEOUT = 2
org_login.start("production"); pid = None
s = wait_state({"error", "success"}, 15)
pid = int(open(os.path.join(HERE, "stub_pid.txt")).read())
check("timeout -> error with message", s["state"] == "error" and "minutes" in s["message"] or "No login" in s.get("message", ""), str(s))
time.sleep(1); check("timeout kills the CLI too", not alive(pid))
org_login.LOGIN_TIMEOUT = 300

# ---- missing CLI -------------------------------------------------------------------------------------
sf_cli.SF_CLI = None
import platform_env
real_find = sf_cli._find_sf_cli
sf_cli._find_sf_cli = lambda: (_ for _ in ()).throw(FileNotFoundError("Could not find 'sf' or 'sfdx'."))
try:
    org_login.start("production"); check("missing CLI raises FileNotFoundError", False, "no error")
except FileNotFoundError:
    check("missing CLI raises FileNotFoundError", True)
sf_cli._find_sf_cli = real_find
sf_cli.SF_CLI = os.path.abspath(os.path.join(FIXTURES, "stub_sf.cmd"))

# ---- HTTP endpoints -------------------------------------------------------------------------------------
from fastapi.testclient import TestClient
import main
tc = TestClient(main.app)
r = tc.get("/api/org-login/options")
check("GET options", r.status_code == 200 and [x["type"] for x in r.json()["options"]] == ["production", "test"], r.text)
check("GET status idle-or-done", tc.get("/api/org-login").status_code == 200)
r = tc.post("/api/org-login", json={"type": "evil"})
check("POST bad type -> 400", r.status_code == 400, r.text)
mode("hang")
r = tc.post("/api/org-login", json={"type": "test", "url": "https://attacker.example", "alias": "x"})
check("POST ok; extra url/alias fields are ignored", r.status_code == 200 and r.json()["url"] == "https://test.salesforce.com" and r.json()["alias"] == "avio-dev", r.text)
check("POST returns the equivalent command", r.json().get("command", "").startswith("sf org login web --instance-url https://test.salesforce.com"), r.text)
time.sleep(1)
check("the CLI got the safe values", args()[4] == "https://test.salesforce.com" and args()[6] == "avio-dev", str(args()))
r = tc.post("/api/org-login", json={"type": "production"})
check("POST while running -> 409", r.status_code == 409, r.text)
r = tc.post("/api/org-login/cancel")
check("POST cancel", r.status_code == 200 and r.json()["state"] == "cancelled", r.text)
time.sleep(1)
sf_cli.SF_CLI = None; sf_cli._find_sf_cli = lambda: (_ for _ in ()).throw(FileNotFoundError("Could not find 'sf' or 'sfdx'."))
r = tc.post("/api/org-login", json={"type": "production"})
check("missing CLI -> 503 with the 'Could not find' text the UI keys on", r.status_code == 503 and "Could not find" in r.text, r.text)

print("\nfailures:", fails)
sys.exit(1 if fails else 0)
