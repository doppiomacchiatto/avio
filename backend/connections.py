"""
connections.py — saved AI provider "connections".

A connection is a label, a provider preset, a base URL and a default model. Its API key is
kept in the OS keystore (see secret_store.py), never in config.json:

    config.json   "connections": [{"id", "label", "preset", "base_url", "model"}, ...]
                  "default_connection": "<id>"
    keystore      service "Avio", account "connection-<id>"

Each AI panel can pick a connection, so one session can use OpenAI and another Claude.
Keys are never returned by any function that feeds an HTTP response: list_connections()
exposes only key_set and a masked hint.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Optional

import ai_client
import secret_store
from ai_client import Resolved, _is_local

log = logging.getLogger(__name__)

_lock = threading.RLock()


class UnknownConnection(KeyError):
    pass


# ---------------------------------------------------------------------------
# config.json access (connections metadata only; no secrets)
# ---------------------------------------------------------------------------

def _read() -> dict:
    return ai_client._load_avio_config()


def _write(cfg: dict) -> None:
    ai_client.CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _account(conn_id: str) -> str:
    return f"connection-{conn_id}"


def _preset_label(preset_id: str) -> str:
    for p in ai_client.PROVIDER_PRESETS:
        if p["id"] == preset_id:
            return p["label"].split(" (")[0]
    return "Custom"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "connection"


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _public(c: dict) -> dict:
    """A connection as the UI sees it: metadata + key status, never the key."""
    key = secret_store.get(_account(c["id"]))
    base_url = c.get("base_url", "")
    return {
        "id": c["id"],
        "label": c.get("label", ""),
        "preset": c.get("preset", "custom"),
        "base_url": base_url,
        "model": c.get("model", ""),
        "key_set": bool(key),
        "key_hint": ("…" + key[-4:]) if key and len(key) >= 8 else ("set" if key else ""),
        "requires_key": not _is_local(base_url),
    }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _records() -> list[dict]:
    recs = _read().get("connections")
    return [c for c in recs if isinstance(c, dict) and c.get("id")] if isinstance(recs, list) else []


def default_id() -> Optional[str]:
    recs = _records()
    want = _read().get("default_connection")
    if want and any(c["id"] == want for c in recs):
        return want
    return recs[0]["id"] if recs else None


def list_connections() -> list[dict]:
    return [_public(c) for c in _records()]


def get_connection(conn_id: str) -> Optional[dict]:
    for c in _records():
        if c["id"] == conn_id:
            return _public(c)
    return None


def status() -> dict:
    """Where keys are stored right now (for the Settings screen)."""
    return secret_store.status()


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------

def upsert(*, conn_id: Optional[str] = None, label: str = "", preset: str = "custom",
           base_url: str = "", model: str = "", api_key: Optional[str] = None,
           clear_key: bool = False, make_default: bool = False) -> dict:
    """Create (conn_id=None) or update a connection. A blank/None api_key keeps the stored
    key; clear_key=True removes it. Returns the public view of the connection."""
    base_url = (base_url or "").strip()
    if not re.match(r"^https?://\S+$", base_url):
        raise ValueError("The gateway URL must start with http:// or https://")
    label = (label or "").strip() or _preset_label(preset)

    with _lock:
        cfg = _read()
        recs = [c for c in cfg.get("connections", []) if isinstance(c, dict) and c.get("id")]
        existing = next((c for c in recs if c["id"] == conn_id), None) if conn_id else None
        if conn_id and not existing:
            raise UnknownConnection(conn_id)

        if existing is None:
            taken = {c["id"] for c in recs}
            base, n = _slug(label), 1
            new_id = base
            while new_id in taken:
                n += 1
                new_id = f"{base}-{n}"
            existing = {"id": new_id}
            recs.append(existing)
        existing.update({"label": label, "preset": preset or "custom",
                         "base_url": base_url, "model": (model or "").strip()})

        cfg["connections"] = recs
        if make_default:
            cfg["default_connection"] = existing["id"]
        elif cfg.get("default_connection") not in {c["id"] for c in recs}:
            cfg["default_connection"] = recs[0]["id"]     # first connection becomes the default
        _write(cfg)

        if clear_key:
            secret_store.delete(_account(existing["id"]))
        elif api_key is not None and api_key.strip():
            secret_store.set(_account(existing["id"]), api_key.strip())
        return _public(existing)


def delete(conn_id: str) -> None:
    with _lock:
        cfg = _read()
        recs = [c for c in cfg.get("connections", []) if isinstance(c, dict) and c.get("id")]
        if not any(c["id"] == conn_id for c in recs):
            raise UnknownConnection(conn_id)
        recs = [c for c in recs if c["id"] != conn_id]
        cfg["connections"] = recs
        if cfg.get("default_connection") == conn_id:
            cfg["default_connection"] = recs[0]["id"] if recs else ""
        _write(cfg)
        secret_store.delete(_account(conn_id))


def set_default(conn_id: str) -> None:
    with _lock:
        cfg = _read()
        if not any(isinstance(c, dict) and c.get("id") == conn_id for c in cfg.get("connections", [])):
            raise UnknownConnection(conn_id)
        cfg["default_connection"] = conn_id
        _write(cfg)


def key_for(conn_id: str) -> Optional[str]:
    """The stored key, for server-side use only (never put this in a response)."""
    return secret_store.get(_account(conn_id))


# ---------------------------------------------------------------------------
# Resolution: which provider settings does a request use?
# ---------------------------------------------------------------------------

def _resolved_from(c: dict) -> Resolved:
    base_url = c.get("base_url", "")
    label = c.get("label") or c["id"]
    model = (c.get("model") or "").strip()
    if not model:
        raise RuntimeError(f"No model is chosen for connection '{label}'. Open ⚙ Settings, pick it and choose a model.")
    key = secret_store.get(_account(c["id"])) or ""
    if not key and not _is_local(base_url):
        raise RuntimeError(f"No API key is saved for connection '{label}'. Open ⚙ Settings and add one.")
    return Resolved(base_url=base_url, model=model, api_key=key, conn_id=c["id"], label=label)


def resolve(conn_id: Optional[str] = None) -> Resolved:
    """
    conn_id given   -> that connection (UnknownConnection if it was deleted); developer
                       overrides are ignored.
    conn_id absent  -> the default connection, with any developer override (opencode.config.json
                       / OPENCODE_* env) applied on top; with no connections at all, the
                       legacy single-key setup.
    Raises RuntimeError with a user-readable message when a key or model is missing.
    """
    if conn_id:
        c = next((c for c in _records() if c["id"] == conn_id), None)
        if c is None:
            raise UnknownConnection(conn_id)
        return _resolved_from(c)

    d_id = default_id()
    if not d_id:
        return ai_client.resolve_legacy()
    d = next(c for c in _records() if c["id"] == d_id)
    ov = ai_client.dev_overrides()
    if not ov:
        return _resolved_from(d)

    url = ov.get("base_url") or d.get("base_url", "")
    model = ov.get("model") or (d.get("model") or "").strip()
    key = ov.get("api_key") or ""
    if not key and _norm_url(url) == _norm_url(d.get("base_url", "")):
        key = secret_store.get(_account(d_id)) or ""      # same host: the connection's key is safe to use
    # An override that points at a different host never borrows the connection's key.
    if not model:
        raise RuntimeError("No model is chosen. Open ⚙ Settings and pick one.")
    if not key and not _is_local(url):
        raise RuntimeError("No API key is available for the overridden gateway URL. "
                           "Set OPENCODE_API_KEY or add api_key to opencode.config.json.")
    return Resolved(base_url=url, model=model, api_key=key, conn_id=d_id, label=d.get("label") or d_id)


# ---------------------------------------------------------------------------
# One-time migration of the old single plain-text key
# ---------------------------------------------------------------------------

# With no saved URL the OpenAI SDK talks to api.openai.com, so the key prefix tells us which
# provider a legacy key belongs to; unknown prefixes fall back to OpenAI.
_KEY_PREFIX_PRESETS = (("oc_sk_", "opencode"), ("sk-ant-", "anthropic"), ("sk-or-", "openrouter"),
                       ("AIza", "google"), ("gsk_", "groq"), ("sk-", "openai"))


def _preset_for(base_url: str, key: str) -> str:
    url = _norm_url(base_url)
    for p in ai_client.PROVIDER_PRESETS:
        if p["base_url"] and _norm_url(p["base_url"]) == url:
            return p["id"]
    if not url:
        for prefix, preset in _KEY_PREFIX_PRESETS:
            if key.startswith(prefix):
                return preset
        return "openai"
    return "custom"


def migrate_legacy() -> Optional[str]:
    """
    If there are no connections yet but the old plain-text key file exists, turn it into a
    'Default' connection: the key goes into the keystore, then the plain file is deleted,
    but only after the keystore returns exactly what was stored. Idempotent. Returns the new
    connection id, or None when there was nothing to do (or the key could not be moved safely,
    in which case the old file is left alone).
    """
    with _lock:
        if _records():
            return None
        path = ai_client.API_KEY_PATH
        try:
            key = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        except OSError:
            key = ""
        if not key:
            return None
        cfg = _read()
        base_url = (cfg.get("base_url") or "").strip()
        preset = _preset_for(base_url, key)
        if not base_url:
            base_url = next((p["base_url"] for p in ai_client.PROVIDER_PRESETS
                             if p["id"] == preset and p["base_url"]), "https://api.openai.com/v1")
        try:
            conn = upsert(label=_preset_label(preset), preset=preset, base_url=base_url,
                          model=(cfg.get("model") or "").strip(), api_key=key, make_default=True)
        except Exception as e:
            log.warning("connections: could not migrate the saved key (%s); leaving it in place", type(e).__name__)
            return None
        if secret_store.get(_account(conn["id"])) != key:        # verify before deleting anything
            log.warning("connections: keystore read-back mismatch; leaving the old key file in place")
            return conn["id"]
        try:
            path.unlink()
        except OSError:
            pass
        # model/base_url now live on the connection; stop leaving stale copies in the legacy fields
        cfg = _read()
        cfg.pop("model", None)
        cfg.pop("base_url", None)
        _write(cfg)
        log.info("connections: moved the saved API key into %s as connection '%s'", status()["label"], conn["id"])
        return conn["id"]
