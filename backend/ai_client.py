"""
OpenCode AI client — provider-agnostic, OpenAI-compatible API.

Supports any provider that exposes an OpenAI-compatible chat completions
endpoint (OpenAI, Anthropic via compat layer, Azure OpenAI, local Ollama,
custom gateways, etc.).

Config priority (highest → lowest):
  1. opencode.config.json  in project root (developer override, git-ignored;
     copy opencode.config.example.json to create it)
  2. OPENCODE_API_KEY / OPENCODE_BASE_URL / OPENCODE_MODEL env vars
  3. <Avio data dir>/api_key   (written by Avio Settings modal)
  4. <Avio data dir>/config.json  model / base_url fields
  5. Legacy ~/.sf_tools_config.json  (old SOQL Explorer config)

Optional config.json keys: "max_tokens" (reply limit), "skills_inject",
"skills_local_budget" (see sf_skills.py). OPENCODE_MAX_TOKENS overrides max_tokens.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional

import openai
from platform_env import avio_data_dir

DEFAULT_MODEL    = "gpt-4o"
# Reasoning models spend part of the limit on hidden thinking (a 4096 limit cut a Claude
# Apex answer off mid-code), so cloud providers get a generous limit. Local servers
# usually run with a ~4K context, so a bigger limit would not help there.
CLOUD_MAX_TOKENS = 16384
LOCAL_MAX_TOKENS = 4096
# If a model rejects the limit as too large, retry with the next smaller value.
_MAX_TOKEN_LADDER = (16384, 8192, 4096, 2048)

CONFIG_PATH      = avio_data_dir() / "config.json"
API_KEY_PATH     = avio_data_dir() / "api_key"
OPENCODE_GATEWAY_URL = "https://opencode.ai/inference/openai/v1"
LEGACY_CFG_PATH  = Path.home() / ".sf_tools_config.json"   # legacy — read-only fallback

# opencode.config.json is looked for relative to the project root.
# In production (bundled app) it can sit next to the binary; in dev it lives
# in the repo root. We walk up from __file__ to find it.
def _find_opencode_config() -> Optional[Path]:
    here = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = here / "opencode.config.json"
        if candidate.exists():
            return candidate
        here = here.parent
    return None


def _load_opencode_config() -> dict:
    p = _find_opencode_config()
    if p:
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def _load_avio_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    return {}


def _load_legacy_config() -> dict:
    try:
        if LEGACY_CFG_PATH.exists():
            return json.loads(LEGACY_CFG_PATH.read_text())
    except Exception:
        pass
    return {}


def save_config(
    model:          str  = "",
    base_url:       str  = "",
    theme:          Optional[str]  = None,
    skills_enabled: Optional[bool] = None,
    skills_source:  Optional[str]  = None,
    skills_path:    Optional[str]  = None,
    skills_url:     Optional[str]  = None,
    custom_skills:  Optional[list] = None,
) -> None:
    """Merge model/base_url/theme/skills settings into ~/.avio_config.json."""
    cfg = _load_avio_config()
    if model:
        cfg["model"] = model
    if base_url is not None:
        cfg["base_url"] = base_url
    if theme is not None:
        cfg["theme"] = theme
    if skills_enabled is not None:
        cfg["skills_enabled"] = skills_enabled
    if skills_source is not None:
        cfg["skills_source"] = skills_source
    if skills_path is not None:
        cfg["skills_path"] = skills_path
    if skills_url is not None:
        cfg["skills_url"] = skills_url
    if custom_skills is not None:
        cfg["custom_skills"] = custom_skills
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _load_api_key() -> str:
    """Return API key from the first available source."""
    # 1. opencode.config.json
    oc = _load_opencode_config()
    if oc.get("api_key"):
        return oc["api_key"].strip()
    # 2. env var
    key = os.environ.get("OPENCODE_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key.strip()
    # 3. ~/.avio_api_key
    if API_KEY_PATH.exists():
        key = API_KEY_PATH.read_text().strip()
        if key:
            return key
    # 4. legacy dotfile paths (read-only fallback for existing installs)
    legacy_key_path = Path.home() / ".avio_api_key"
    if not legacy_key_path.exists():
        legacy_key_path = Path.home() / ".anthropic_key"
    if legacy_key_path.exists():
        key = legacy_key_path.read_text().strip()
        if key:
            return key
    # 5. legacy config file
    legacy = _load_legacy_config()
    key = legacy.get("api_key", "").strip()
    if key:
        return key
    raise RuntimeError(
        "No API key is configured. Open ⚙ Settings, add an AI connection and paste your key "
        "(or set the OPENCODE_API_KEY environment variable)."
    )


def _load_base_url() -> str:
    """Return base_url from the first available source."""
    oc = _load_opencode_config()
    if oc.get("base_url"):
        return oc["base_url"].strip()
    url = os.environ.get("OPENCODE_BASE_URL", "")
    if url:
        return url.strip()
    cfg = _load_avio_config()
    url = cfg.get("base_url", "").strip()
    if url:
        return url
    legacy = _load_legacy_config()
    url = legacy.get("base_url", "").strip()
    if url:
        return url
    # OpenCode Console personal API keys (oc_sk_…) only work on OpenCode's gateway
    try:
        if _load_api_key().startswith("oc_sk_"):
            return OPENCODE_GATEWAY_URL
    except RuntimeError:
        pass
    return ""


def _load_model() -> str:
    """Return model from the first available source."""
    oc = _load_opencode_config()
    if oc.get("model"):
        return oc["model"].strip()
    model = os.environ.get("OPENCODE_MODEL", "")
    if model:
        return model.strip()
    cfg = _load_avio_config()
    return cfg.get("model", "").strip() or DEFAULT_MODEL


@dataclass(frozen=True)
class Resolved:
    """Everything needed to talk to one provider: a saved connection (see connections.py)
    or the legacy single-key configuration."""
    base_url: str
    model: str
    api_key: str
    conn_id: Optional[str] = None
    label: str = ""

    @property
    def local(self) -> bool:
        return _is_local(self.base_url)


def dev_overrides() -> dict:
    """Fields set by opencode.config.json (first) or an OPENCODE_* environment variable:
    any of api_key, base_url, model. These developer overrides apply on top of the default
    connection, as they always beat Settings; an explicitly chosen connection ignores them."""
    oc = _load_opencode_config()
    out = {}
    for field, env in (("api_key", "OPENCODE_API_KEY"), ("base_url", "OPENCODE_BASE_URL"), ("model", "OPENCODE_MODEL")):
        value = (oc.get(field) or "").strip() or os.environ.get(env, "").strip()
        if value:
            out[field] = value
    return out


def has_dev_override() -> bool:
    return bool(dev_overrides())


def resolve_legacy() -> Resolved:
    """Provider settings from the pre-connections sources (override file, env vars,
    config.json, legacy dotfiles). Raises RuntimeError with a helpful message if no key."""
    url = _load_base_url()
    try:
        key = _load_api_key()
    except RuntimeError:
        if not _is_local(url):
            raise                 # a cloud provider needs a key
        key = ""                  # Ollama / LM Studio run without one
    return Resolved(base_url=url, model=_load_model(), api_key=key)


# Presets shown in Settings. Every one speaks the OpenAI-compatible API
# (chat/completions + /models); Azure OpenAI is not included because it needs
# per-deployment URLs and an api-version.
PROVIDER_PRESETS = [
    {"id": "opencode",   "label": "OpenCode (Console gateway)",       "base_url": OPENCODE_GATEWAY_URL,                                       "key_hint": "oc_sk_…"},
    {"id": "openai",     "label": "OpenAI (ChatGPT models)",          "base_url": "https://api.openai.com/v1",                                "key_hint": "sk-…"},
    {"id": "anthropic",  "label": "Anthropic (Claude)",               "base_url": "https://api.anthropic.com/v1",                             "key_hint": "sk-ant-…"},
    {"id": "google",     "label": "Google (Gemini)",                  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",  "key_hint": "AIza…"},
    {"id": "openrouter", "label": "OpenRouter (Llama and many more)", "base_url": "https://openrouter.ai/api/v1",                             "key_hint": "sk-or-…"},
    {"id": "groq",       "label": "Groq (Llama, fast)",               "base_url": "https://api.groq.com/openai/v1",                           "key_hint": "gsk_…"},
    {"id": "ollama",     "label": "Ollama (local Llama)",             "base_url": "http://localhost:11434/v1",                                "key_hint": "not needed", "needs_key": False},
    {"id": "custom",     "label": "Custom gateway",                   "base_url": "",                                                         "key_hint": "your gateway key"},
]

_NON_CHAT_HINTS = ("embed", "whisper", "tts", "dall-e", "moderation", "davinci", "babbage",
                   "transcribe", "realtime", "rerank", "image", "audio")


def _is_local(url: str) -> bool:
    return any(h in (url or "") for h in ("localhost", "127.0.0.1", "[::1]"))


def is_local_provider() -> bool:
    """True when the configured base URL is a local server (Ollama, LM Studio, ...)."""
    return _is_local(_load_base_url())


def _load_max_tokens(url: str) -> int:
    """Reply limit: OPENCODE_MAX_TOKENS, then config.json "max_tokens", then a per-provider default."""
    for raw in (os.environ.get("OPENCODE_MAX_TOKENS"), _load_avio_config().get("max_tokens")):
        try:
            n = int(raw)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    return LOCAL_MAX_TOKENS if _is_local(url) else CLOUD_MAX_TOKENS


@dataclass
class StreamFinish:
    """Yielded last by AIClient.stream(): why the model stopped ("stop", "length", ...)."""
    reason: Optional[str]

    @property
    def truncated(self) -> bool:
        return self.reason == "length"   # hit the token limit; the answer is incomplete


def _client_kwargs(api_key: str, url: str) -> dict:
    """Constructor kwargs for openai.OpenAI, with per-vendor quirks applied."""
    key = (api_key or "").strip()
    if not key:
        if _is_local(url):
            key = "not-needed"   # Ollama / LM Studio ignore the key but the SDK requires one
        else:
            key = _load_api_key()   # raises a helpful error if none is configured
    kwargs: dict = {"api_key": key}
    if url:
        kwargs["base_url"] = url
    if "anthropic.com" in url:
        # Anthropic's /models endpoint rejects requests without a version header
        kwargs["default_headers"] = {"anthropic-version": "2023-06-01"}
    return kwargs


def needs_key(url: str) -> bool:
    return not _is_local(url)


def fetch_models(api_key: Optional[str] = None, base_url: Optional[str] = None) -> list[str]:
    """List chat-capable model ids from the provider's OpenAI-compatible /models endpoint.

    Pass api_key/base_url to test unsaved Settings values; otherwise the saved
    config is used. Raises on failure so the caller can fall back.
    """
    url = (base_url or "").strip() or _load_base_url()
    key = (api_key or "").strip()
    if not key and url.rstrip("/") == OPENCODE_GATEWAY_URL.rstrip("/"):
        # OpenCode's model catalog is public: it answers a request with no Authorization header
        # (and rejects a made-up key), so list it without one. The full list then shows as soon
        # as the provider is chosen, before any key is entered.
        raw_ids = _fetch_public_model_ids(url)
    else:
        # Don't mix a typed-in URL with a different vendor's saved key by accident: a blank
        # key falls back to the saved one, which is the normal "just refresh" case.
        kwargs = _client_kwargs(key, url)
        kwargs.update(timeout=10.0, max_retries=0)
        raw_ids = [m.id for m in openai.OpenAI(**kwargs).models.list().data]
    ids = []
    for rid in raw_ids:
        mid = rid.removeprefix("models/")   # Gemini prefixes ids with "models/"
        if not any(h in mid.lower() for h in _NON_CHAT_HINTS):
            ids.append(mid)
    if "anthropic.com" not in url:
        ids.sort(key=str.lower)   # Anthropic already returns newest first
    return ids


def _fetch_public_model_ids(url: str) -> list[str]:
    """GET <url>/models with no credentials and return the model ids (OpenAI list format)."""
    import urllib.request
    req = urllib.request.Request(url.rstrip("/") + "/models", headers={"User-Agent": "Avio"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]


class AIClient:
    def __init__(self):
        # One SDK client per (URL, key): different panels can use different connections at once.
        self._clients: dict = {}

    def invalidate(self) -> None:
        """Drop cached clients (call after connections or keys change)."""
        self._clients.clear()

    def _client_for(self, r: Resolved) -> openai.OpenAI:
        key = (r.base_url, hashlib.sha256(r.api_key.encode("utf-8")).hexdigest()[:16])
        client = self._clients.get(key)
        if client is None:
            client = openai.OpenAI(**_client_kwargs(r.api_key, r.base_url))
            self._clients[key] = client
        return client

    @staticmethod
    def _prepare(messages: list[dict], system: Optional[str]) -> list[dict]:
        """System prompt + messages, keeping only role/content. The UI stores extra fields
        on messages (e.g. `system: true`), which strict providers reject."""
        full: list[dict] = []
        if system:
            full.append({"role": "system", "content": system})
        for m in messages:
            full.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        return full

    def _create(self, r: Resolved, model: str, messages: list[dict], max_tokens: int, stream: bool):
        """chat.completions.create with two compatibility retries on a 400 about the limit:
        providers differ on the parameter name (OpenAI's newer models want
        max_completion_tokens and reject max_tokens) and on the largest allowed value."""
        client = self._client_for(r)
        param = "max_completion_tokens" if "api.openai.com" in r.base_url else "max_tokens"
        switched = False
        for _ in range(5):
            try:
                return client.chat.completions.create(
                    model=model, messages=messages, stream=stream, **{param: max_tokens})
            except openai.BadRequestError as e:
                msg = str(e).lower()
                if "max_tokens" not in msg and "max_completion_tokens" not in msg:
                    raise
                other = "max_tokens" if param == "max_completion_tokens" else "max_completion_tokens"
                if not switched and other in msg and ("unsupported" in msg or "not supported" in msg):
                    param, switched = other, True
                    continue
                smaller = next((n for n in _MAX_TOKEN_LADDER if n < max_tokens), None)
                if smaller is None:
                    raise
                max_tokens = smaller
        raise RuntimeError("could not find a token limit the provider accepts")

    # ------------------------------------------------------------------
    # One-shot (returns full text)
    # ------------------------------------------------------------------
    def ask(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        resolved: Optional[Resolved] = None,
    ) -> str:
        r = resolved or resolve_legacy()
        resp = self._create(
            r,
            model or r.model,
            self._prepare(messages, system),
            max_tokens or _load_max_tokens(r.base_url),
            stream=False,
        )
        return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Streaming (yields text deltas, then one StreamFinish)
    # ------------------------------------------------------------------
    def stream(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        resolved: Optional[Resolved] = None,
    ) -> Generator[object, None, None]:
        r = resolved or resolve_legacy()
        finish: Optional[str] = None
        with self._create(
            r,
            model or r.model,
            self._prepare(messages, system),
            max_tokens or _load_max_tokens(r.base_url),
            stream=True,
        ) as stream:
            for chunk in stream:
                if not chunk.choices:        # e.g. Azure's leading chunk, or a usage-only chunk
                    continue
                choice = chunk.choices[0]
                if choice.delta.content:
                    yield choice.delta.content
                if choice.finish_reason:
                    finish = choice.finish_reason
        yield StreamFinish(finish)
