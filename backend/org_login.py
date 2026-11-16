"""
org_login.py — first-run Salesforce login through the sf CLI.

Runs `sf org login web --instance-url <url> --alias <alias>` as a background job so the UI can
offer "Log in" when no org has been authenticated yet. The page only ever says which kind of org
(production or test); the URL and alias are chosen here, so nothing the page sends can point the
CLI at an arbitrary address. Airgapped and other special environments override the URLs in
config.json:

    "org_login_urls": {"production": "https://login.example.mil", "test": "https://test.example.mil"}
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from typing import Optional
from urllib.parse import urlparse

import sf_cli
from ai_client import _load_avio_config

log = logging.getLogger(__name__)

# kind -> (alias, default login URL)
ORG_TYPES: dict[str, tuple[str, str]] = {
    "production": ("avio-prod", "https://login.salesforce.com"),
    "test":       ("avio-dev",  "https://test.salesforce.com"),
}

LOGIN_TIMEOUT = 300          # seconds the user has to finish in the browser
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _valid_url(url: object) -> Optional[str]:
    """A normalised https URL (no trailing slash), or None. http is refused: the OAuth login
    would send credentials in clear text."""
    if not isinstance(url, str):
        return None
    url = url.strip().rstrip("/")
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or any(c.isspace() for c in url) or url.startswith("-"):
        return None
    return url


def login_options() -> list[dict]:
    """The org types the UI can offer, with the URL each would use and whether config.json
    overrides it."""
    cfg = _load_avio_config().get("org_login_urls")
    cfg = cfg if isinstance(cfg, dict) else {}
    out = []
    for kind, (alias, default_url) in ORG_TYPES.items():
        custom = _valid_url(cfg.get(kind)) if cfg.get(kind) else None
        if cfg.get(kind) and not custom:
            log.warning("org_login_urls.%s is not a valid https URL; using %s", kind, default_url)
        out.append({"type": kind, "alias": alias, "url": custom or default_url, "custom": bool(custom)})
    return out


def _option(kind: str) -> dict:
    for o in login_options():
        if o["type"] == kind:
            return o
    raise ValueError("Choose production or test.")


def command_text(kind: str) -> str:
    """The equivalent command, for people who prefer to run it themselves."""
    o = _option(kind)
    return f"sf org login web --instance-url {o['url']} --alias {o['alias']}"


# ---------------------------------------------------------------------------
# One login job at a time
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_job: dict = {"state": "idle"}          # idle | running | success | error | cancelled
_proc: Optional[subprocess.Popen] = None


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop the CLI and everything it started. On Windows `sf` is a .cmd wrapper around node, so
    killing only the wrapper would leave node holding the OAuth callback port (1717)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception as e:
        log.debug("org_login: kill failed: %s", e)
        try:
            proc.kill()
        except Exception:
            pass


def status() -> dict:
    with _lock:
        j = dict(_job)
    if j.get("state") == "running":
        j["elapsed"] = int(time.time() - j.get("started", time.time()))
    j.pop("started", None)
    return j


def start(kind: str) -> dict:
    """Start the browser login. Raises ValueError for a bad type, RuntimeError if a login is
    already waiting or the CLI is missing."""
    global _proc
    opt = _option(kind)
    with _lock:
        if _job.get("state") == "running":
            raise RuntimeError("A login is already waiting for you in the browser.")
        if sf_cli.SF_CLI is None:
            sf_cli.SF_CLI = sf_cli._find_sf_cli()          # FileNotFoundError if absent
        cmd = [sf_cli.SF_CLI, "org", "login", "web",
               "--instance-url", opt["url"], "--alias", opt["alias"], "--json"]
        kw = {k: v for k, v in sf_cli.SUBPROCESS_KWARGS.items() if k != "capture_output"}
        if os.name != "nt":
            kw["start_new_session"] = True
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env={**os.environ, "PATH": sf_cli._augmented_path()}, **kw)
        _proc = proc
        _job.clear()
        _job.update(state="running", type=kind, alias=opt["alias"], url=opt["url"], started=time.time())
    threading.Thread(target=_wait, args=(proc, kind), daemon=True).start()
    return status()


def _wait(proc: subprocess.Popen, kind: str) -> None:
    timed_out = False
    try:
        out, err = proc.communicate(timeout=LOGIN_TIMEOUT)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        out, err = proc.communicate()
    result = _summarise(out or "", err or "", proc.returncode, timed_out)
    with _lock:
        if _proc is not proc or _job.get("state") != "running":
            return                                          # cancelled (or superseded) meanwhile
        _job.update(result)


def _summarise(out: str, err: str, rc: Optional[int], timed_out: bool) -> dict:
    """Reduce the CLI's output to a state and a message. The raw output is never kept or
    logged: a successful `--json` login result can contain tokens."""
    if timed_out:
        return {"state": "error",
                "message": f"No login was completed within {LOGIN_TIMEOUT // 60} minutes. Try again."}
    clean = _ANSI_RE.sub("", out).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and data.get("status") == 0:
        res = data.get("result") if isinstance(data.get("result"), dict) else {}
        return {"state": "success", "username": res.get("username") or ""}
    if isinstance(data, dict):
        msg = str(data.get("message") or data.get("name") or "The login failed.")
    else:
        msg = _ANSI_RE.sub("", err).strip().splitlines()[-1] if err.strip() else f"The sf CLI exited with code {rc}."
    return {"state": "error", "message": msg[:400]}


def cancel() -> dict:
    with _lock:
        proc = _proc
        running = _job.get("state") == "running"
        if running:
            _job.update(state="cancelled")
    if running and proc is not None:
        _kill_tree(proc)
    return status()
