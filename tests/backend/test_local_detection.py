"""Which base URLs count as a local model server (condensed skills, local reply limit and timeout,
no key needed): ai_client.is_local_url against the table shared with the frontend suite, plus the
per-connection "local" override in config.json."""
import os, sys, json, shutil, tempfile
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp                       # isolate Avio config / secrets from the real ones
os.environ["AVIO_SECRET_BACKEND"] = "file"
for k in ("OPENCODE_API_KEY", "OPENCODE_BASE_URL", "OPENCODE_MODEL", "AVIO_API_TOKEN", "ANTHROPIC_API_KEY",
          "OPENCODE_MAX_TOKENS"):
    os.environ.pop(k, None)
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

import ai_client, connections
from ai_client import Resolved

fails = 0
def check(name, cond, detail=""):
    global fails
    fails += (not cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail and not cond else ""))

table = json.loads((REPO / "tests" / "fixtures" / "local_urls.json").read_text(encoding="utf-8"))["cases"]
for url, want in table:
    got = ai_client.is_local_url(url)
    check(f"is_local_url {url!r} -> {'local' if want else 'cloud'}", got is want, f"got {got}")
    check(f"_is_local {url!r} agrees with no override", ai_client._is_local(url) is want)
check("is_local_url(None) is cloud", ai_client.is_local_url(None) is False)

# Every built-in cloud preset stays cloud, so their behaviour is unchanged.
for p in ai_client.PROVIDER_PRESETS:
    urls = [p["base_url"]] + [r["base_url"] for r in p.get("regions", [])]
    for u in [u for u in urls if u]:
        check(f"preset {p['id']} {u}: {'local' if p.get('needs_key') is False else 'cloud'}",
              ai_client.is_local_url(u) is (p.get("needs_key") is False))

# What follows from "local": reply limit, chat timeout, key requirement.
LAN = "http://192.168.1.50:11434/v1"
check("LAN Ollama gets the local reply limit", ai_client._load_max_tokens(LAN) == ai_client.LOCAL_MAX_TOKENS)
check("LAN Ollama gets the local chat timeout", ai_client._load_chat_timeout(LAN) == ai_client.LOCAL_CHAT_TIMEOUT)
check("cloud keeps the cloud chat timeout", ai_client._load_chat_timeout("https://api.openai.com/v1") == ai_client.CLOUD_CHAT_TIMEOUT)
check("LAN Ollama needs no key", ai_client.needs_key(LAN) is False and ai_client.needs_key("https://api.openai.com/v1") is True)
check("Resolved.local for a Docker host", Resolved(base_url="http://host.docker.internal:11434/v1", model="m", api_key="").local is True)

# Per-connection override ("local": true/false in config.json, not in the UI).
cfg_path = ai_client.CONFIG_PATH
GW = "https://llm.example.com/v1"      # a self-hosted Ollama behind a public name
cfg_path.write_text(json.dumps({"connections": [
    {"id": "gw", "label": "GW", "preset": "custom", "base_url": GW + "/", "model": "llama3", "local": True},
    {"id": "lan", "label": "LAN", "preset": "custom", "base_url": LAN, "model": "llama3", "local": False},
    {"id": "plain", "label": "Plain", "preset": "custom", "base_url": "http://ollama:11434/v1", "model": "llama3"},
], "default_connection": "gw"}))
check("override local:true makes a public name local", ai_client._is_local(GW) is True)
check("override ignores a trailing slash difference", ai_client._is_local(GW + "/") is True)
check("override local:false makes a LAN address cloud", ai_client._is_local(LAN) is False)
check("is_local_url itself ignores overrides", ai_client.is_local_url(GW) is False and ai_client.is_local_url(LAN) is True)
check("no override: the URL rule", ai_client._is_local("http://ollama:11434/v1") is True)
pub = {c["id"]: c for c in connections.list_connections()}
check("UI sees local + requires_key from the override (gw)", pub["gw"]["local"] is True and pub["gw"]["requires_key"] is False, pub["gw"])
check("UI sees local + requires_key from the override (lan)", pub["lan"]["local"] is False and pub["lan"]["requires_key"] is True, pub["lan"])
check("UI sees local from the URL rule (plain)", pub["plain"]["local"] is True)
r = connections.resolve("gw")
check("a local-overridden connection resolves without a key, and is local", r.local is True and r.api_key == "")
try:
    connections.resolve("lan")
    check("a cloud-overridden connection needs a key", False, "resolved without a key")
except RuntimeError as e:
    check("a cloud-overridden connection needs a key", "No API key" in str(e), str(e))
# Editing the connection in Settings keeps the hand-set flag.
connections.upsert(conn_id="gw", label="GW2", preset="custom", base_url=GW, model="llama3:8b")
check("upsert keeps the 'local' flag", next(c for c in json.loads(cfg_path.read_text())["connections"] if c["id"] == "gw").get("local") is True)
cfg_path.write_text(json.dumps({"connections": [{"id": "x", "base_url": GW, "local": "yes"}]}))
check("a non-boolean 'local' is ignored", ai_client._is_local(GW) is False)
cfg_path.write_text(json.dumps({"connections": "garbage"}))
check("a malformed connections list is ignored", ai_client._is_local(LAN) is True)
cfg_path.unlink()

shutil.rmtree(tmp, ignore_errors=True)
print("\nfailures:", fails)
sys.exit(1 if fails else 0)
