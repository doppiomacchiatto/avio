"""
sf_skills.py — Salesforce skill RAG context for the Avio AI chat.

Loads bundled SKILL.md and reference files from backend/sf_skills/ by default.
Supports three source modes (configured via ~/.avio_config.json):

  skills_source = "bundled"  — reads from sf_skills/ next to this file (default)
  skills_source = "path"     — reads from a local directory (skills_path config key)
                               Airgap / internal mirror: point to a network share or
                               a checkout of an internal fork of forcedotcom/sf-skills
  skills_source = "url"      — fetches over HTTP from an internal server (skills_url)
                               Must return the same directory tree as forcedotcom/sf-skills

  skills_enabled = false     — disables augmentation entirely (no files read, no prompt
                               injection). Useful for airgap environments where even
                               local reads are undesirable, or for troubleshooting.

Bundled files are cherry-picked from forcedotcom/sf-skills.
See sf_skills/VERSION for the upstream commit.
"""
from __future__ import annotations

import re
import json
import time
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE       = Path(__file__).resolve().parent
SKILLS_DIR  = _HERE / "sf_skills"          # default bundled location

from platform_env import avio_data_dir as _avio_data_dir
CONFIG_PATH  = _avio_data_dir() / "config.json"
USER_SKILLS  = _avio_data_dir() / "skills"   # downloaded/imported skills live here

# Local models (Ollama, LM Studio) usually run with a ~4K-token context. The full Apex skill
# alone is ~6K tokens, and Ollama silently drops the middle of an over-long prompt, so local
# providers get a condensed summary instead (~1.5K tokens). Configurable: skills_local_budget.
LOCAL_SKILL_BUDGET = 6000

# Skills live under skills/<slug>/ in the forcedotcom/sf-skills repo
GH_RAW_BASE  = "https://raw.githubusercontent.com/forcedotcom/sf-skills/main/skills"

# ---------------------------------------------------------------------------
# Skill file manifest  (relative paths within any skills root directory)
# ---------------------------------------------------------------------------
SKILL_FILES: dict[str, list[str]] = {
    "platform-soql-query": [
        "platform-soql-query/SKILL.md",
        "platform-soql-query/references/anti-patterns.md",
        "platform-soql-query/references/query-optimization.md",
        "platform-soql-query/references/soql-reference.md",
    ],
    "platform-apex-generate": [
        "platform-apex-generate/SKILL.md",
    ],
}

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_skills_config() -> dict:
    """Return the skills-related keys from ~/.avio_config.json."""
    try:
        if CONFIG_PATH.exists():
            raw = json.loads(CONFIG_PATH.read_text())
            return {
                "enabled":       raw.get("skills_enabled", True),
                "source":        raw.get("skills_source",  "bundled"),
                "path":          raw.get("skills_path",    None),
                "url":           raw.get("skills_url",     None),
                "custom_skills": raw.get("custom_skills",  []),
                # "relevant" (default) or "all": which added skills get injected
                "inject":        raw.get("skills_inject",  "relevant"),
                # characters of skill text sent to local models; 0 = none, -1 = no limit
                "local_budget":  raw.get("skills_local_budget", LOCAL_SKILL_BUDGET),
            }
    except Exception as e:
        log.debug("sf_skills: could not read config — %s", e)
    return {"enabled": True, "source": "bundled", "path": None, "url": None,
            "custom_skills": [], "inject": "relevant", "local_budget": LOCAL_SKILL_BUDGET}


def _resolve_skills_root(cfg: dict) -> Optional[Path]:
    """
    Return the root Path to read skill files from, based on config.
    Returns None if the source uses HTTP (github or url) — caller handles fetch.
    """
    source = cfg.get("source", "bundled")

    if source == "bundled":
        return SKILLS_DIR

    if source == "github":
        return None   # fetched from GitHub raw CDN

    if source == "path":
        raw = cfg.get("path") or ""
        p = Path(raw.strip()).expanduser()
        if p.is_dir():
            return p
        log.warning("sf_skills: skills_path '%s' not found — falling back to bundled", p)
        return SKILLS_DIR

    if source == "url":
        return None   # HTTP path handled separately

    log.warning("sf_skills: unknown skills_source '%s' — falling back to bundled", source)
    return SKILLS_DIR


def _effective_base_url(cfg: dict) -> str:
    """Return the HTTP base URL for github or url sources. Empty string otherwise."""
    source = cfg.get("source", "bundled")
    if source == "github":
        return GH_RAW_BASE
    if source == "url":
        return (cfg.get("url") or "").rstrip("/")
    return ""


# ---------------------------------------------------------------------------
# Intent detection  — keyword sets that trigger each skill
# ---------------------------------------------------------------------------
_SOQL_RE = re.compile(
    r"\b(soql|select\s+\w|query|queries|where\s+clause|governor.limit|"
    r"relationship.quer|aggregate|count\s*\(|sosl|query.plan|"
    r"index|selectiv|bulk\s+quer|anti.pattern|from\s+account|"
    r"from\s+contact|from\s+opportunity|from\s+case|from\s+lead|"
    r"from\s+\w+__c|order\s+by|limit\s+\d|subquery)\b",
    re.IGNORECASE,
)

_APEX_RE = re.compile(
    r"\.cls\b|(?<!\w)(apex|trigger|batch\s+apex|queueable|schedulable|"
    r"invocable|aura.enabled|rest.resource|soql.inside.loop|"
    r"bulkif|with.sharing|without.sharing|database\.(insert|update|delete)|"
    r"dml\s+statement|future\s+method|platform.event|apex.class|"
    r"apex.trigger|selector\s+class|service\s+class|domain\s+class|"
    r"test\s+class(es)?|unit\s+tests?|@?istest|code\s+coverage|"
    r"test\s+data\s+factory|testdatafactory|debug\s+logs?)(?!\w)",
    re.IGNORECASE,
)

APEX_SKILL = "platform-apex-generate"
SOQL_SKILL = "platform-soql-query"


def _recent_user_text(messages: list[dict]) -> str:
    """Text of the last few user messages (skills are matched against user text only)."""
    return " ".join(
        m["content"] for m in messages[-6:]
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    )


def detect_skills(messages: list[dict], force: Optional[list[str]] = None) -> list[str]:
    """
    Return list of skill names relevant to the conversation.
    `force` lists skills that are always included (e.g. the Apex Runner forces
    the Apex skill, since its prompts often contain no Apex keyword).
    """
    combined = _recent_user_text(messages)

    skills: list[str] = []
    if SOQL_SKILL in (force or []) or _SOQL_RE.search(combined):
        skills.append(SOQL_SKILL)
    if APEX_SKILL in (force or []) or _APEX_RE.search(combined):
        skills.append(APEX_SKILL)
    return skills


# ---------------------------------------------------------------------------
# File loading — local path and HTTP
# ---------------------------------------------------------------------------

def _load_file_local(root: Path, rel_path: str) -> Optional[str]:
    path = root / rel_path
    if not path.exists():
        log.debug("sf_skills: file not found: %s", path)
        return None
    try:
        content = path.read_text(encoding="utf-8")
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        log.debug("sf_skills: read error %s — %s", path, e)
        return None


# In-memory cache for HTTP skill files (github / url sources). Without it every chat
# message re-downloaded every file. Failures are cached briefly so a missing file or an
# unreachable host does not cost a timeout on every message.
_URL_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_URL_TTL_OK   = 3600.0
_URL_TTL_FAIL = 300.0


def clear_url_cache() -> None:
    _URL_CACHE.clear()


def _load_file_url(base_url: str, rel_path: str, use_cache: bool = True) -> Optional[str]:
    """
    Fetch a skill file from an HTTP server (GitHub raw or an internal mirror).
    base_url should be the root of an sf-skills mirror, e.g.:
      https://skills.internal.corp/sf-skills
    Results are cached (see _URL_CACHE). use_cache=False forces a fresh download
    and refreshes the cache (used when the user explicitly adds a skill).
    """
    import urllib.request
    import urllib.error
    url = base_url.rstrip("/") + "/" + rel_path
    now = time.monotonic()
    if use_cache:
        hit = _URL_CACHE.get(url)
        if hit and now < hit[0]:
            return hit[1]

    content: Optional[str] = None
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            content = resp.read().decode("utf-8")
            if _is_markdown(rel_path):      # HTML comments are markdown noise; leave code files as they are
                content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
            content = content.strip()
    except urllib.error.HTTPError as e:
        # Optional reference files are probed by name, so a 404 is expected.
        (log.debug if e.code == 404 else log.warning)("sf_skills: HTTP %s for %s", e.code, url)
    except Exception as e:
        log.warning("sf_skills: HTTP fetch failed %s — %s", url, e)

    _URL_CACHE[url] = (now + (_URL_TTL_OK if content else _URL_TTL_FAIL), content)
    return content


# Reference files that skills commonly ship; probed by name when SKILL.md does not link them.
_FALLBACK_REFS = [
    "references/anti-patterns.md",
    "references/query-optimization.md",
    "references/soql-reference.md",
    "references/best-practices.md",
    "references/patterns.md",
    "references/reference.md",
    "references/guidelines.md",
    "references/examples.md",
]
_MAX_DISCOVERED_REFS = 40

# Skills link more than markdown: Apex templates, query samples, metadata files. Those are fetched
# and injected too, but only when SKILL.md links to them (the author's own reference list), so a
# skill with a big assets/ folder does not send all of it. Scripts (.py, .sh) are never included.
_ASSET_EXTS = ("cls", "trigger", "apex", "soql", "xml", "json", "yaml", "yml", "txt", "js", "html", "css")
_REF_EXT = "(?:md|" + "|".join(_ASSET_EXTS) + ")"
_MAX_ASSET_CHARS = 30_000          # per non-markdown file; larger ones are skipped
_MD_LINK_RE = re.compile(r"\]\(\s*<?([^)\s>#]+\." + _REF_EXT + r")(?:#[^)\s]*)?>?\s*\)", re.IGNORECASE)
_MD_BARE_RE = re.compile(
    r"(?<![\w/.\\-])((?:references|resources|docs|templates|examples|assets)/[\w./-]+\." + _REF_EXT + r")(?![\w-])",
    re.IGNORECASE,
)


def _is_markdown(rel: str) -> bool:
    return rel.lower().endswith(".md")


def _linked_paths(skill_md: Optional[str]) -> list[str]:
    """Relative paths SKILL.md links to (markdown or an allowed asset type), in order of appearance.
    Only plain relative paths are accepted (no URLs, absolute paths, or `..`)."""
    found: list[str] = []
    if not skill_md:
        return found
    for raw in _MD_LINK_RE.findall(skill_md) + _MD_BARE_RE.findall(skill_md):
        p = raw.strip()
        if "\\" in p or p.startswith(("/", "#")) or re.match(r"^[a-z][a-z0-9+.-]*:", p, re.IGNORECASE):
            continue
        parts = [s for s in p.split("/") if s not in ("", ".")]
        if not parts or ".." in parts:
            continue
        p = "/".join(parts)
        if p.lower() != "skill.md" and p not in found:
            found.append(p)
        if len(found) >= _MAX_DISCOVERED_REFS:
            break
    return found


def _candidate_ref_paths(skill_md: Optional[str]) -> list[str]:
    """Relative paths to download next to SKILL.md: every file SKILL.md links to
    (e.g. `[...](references/foo.md)` or `[...](assets/template.cls)`), then the common
    fallback markdown names."""
    found = _linked_paths(skill_md)
    return found + [p for p in _FALLBACK_REFS if p not in found]


_FENCE_LANG = {"cls": "apex", "trigger": "apex", "apex": "apex", "soql": "sql", "yml": "yaml"}


def _asset_block(rel: str, content: str) -> str:
    """A non-markdown skill file as a labelled code block, so the model knows what it is."""
    ext = rel.rsplit(".", 1)[-1].lower()
    return f"### Skill file: `{rel}`\n\n````{_FENCE_LANG.get(ext, ext)}\n{content.strip()}\n````"


def _read_linked_asset(skill_dir: Path, rel: str) -> Optional[str]:
    """Text of a linked non-markdown file inside skill_dir, or None (missing, too big, outside the
    folder, or unreadable)."""
    try:
        root = skill_dir.resolve()
        f = (skill_dir / rel).resolve()
        if root not in f.parents or not f.is_file() or f.stat().st_size > _MAX_ASSET_CHARS * 4:
            return None
        text = f.read_text(encoding="utf-8")
    except Exception:
        return None
    return text if text.strip() and len(text) <= _MAX_ASSET_CHARS else None


# ---------------------------------------------------------------------------
# Custom skill helpers
# ---------------------------------------------------------------------------

_GH_RAW_BASE = GH_RAW_BASE

def _load_custom_skill_context(entry: dict) -> Optional[str]:
    """
    Load all markdown files for a custom skill entry.
    entry = {"name": "...", "path": "/abs/path/to/skill-dir"}
           or {"name": "...", "path": "https://raw.githubusercontent.com/..."}
           or {"name": "...", "path": "file:///local/path/to/skill-dir"}

    For HTTP(S) paths: fetches SKILL.md and known reference files from the URL base.
    For local paths (including file:// URLs): reads from the filesystem.
    Returns a formatted markdown block or None if the source is inaccessible.
    """
    raw_path = (entry.get("path") or "").strip()
    if not raw_path:
        return None

    name = entry.get("name") or raw_path.rstrip("/").split("/")[-1]

    # ── HTTP(S) source ────────────────────────────────────────────────────────
    if raw_path.startswith("http://") or raw_path.startswith("https://"):
        base_url = raw_path.rstrip("/")
        # SKILL.md first, then the reference files it links to (plus common names)
        skill_md = _load_file_url(base_url, "SKILL.md")
        parts = [skill_md] if skill_md else []
        for rel in _candidate_ref_paths(skill_md):
            content = _load_file_url(base_url, rel)
            if content and (_is_markdown(rel) or len(content) <= _MAX_ASSET_CHARS):
                parts.append(content if _is_markdown(rel) else _asset_block(rel, content))
        if not parts:
            log.warning("sf_skills: custom skill URL returned no content: %s", base_url)
            return None
        return f"## {name} (custom)\n\n" + "\n\n---\n\n".join(parts)

    # ── bundled: sentinel → resolve to SKILLS_DIR/slug ───────────────────────
    if raw_path.startswith("bundled:"):
        slug = raw_path[len("bundled:"):]
        raw_path = str(SKILLS_DIR / slug)

    # ── file:// URL → strip scheme ────────────────────────────────────────────
    if raw_path.startswith("file://"):
        raw_path = raw_path[7:]

    # ── Local filesystem ──────────────────────────────────────────────────────
    root = Path(raw_path).expanduser()
    if not root.is_dir():
        log.warning("sf_skills: custom skill path not found: %s", root)
        return None

    parts = []
    skill_md = root / "SKILL.md"
    if skill_md.exists():
        content = _load_file_local(root, "SKILL.md")
        if content:
            parts.append(content)
    for md in sorted(root.rglob("*.md")):
        if md == skill_md:
            continue
        try:
            content = md.read_text(encoding="utf-8")
            content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).strip()
            if content:
                parts.append(content)
        except Exception as e:
            log.debug("sf_skills: custom skill read error %s — %s", md, e)
    for rel in _linked_paths(parts[0] if parts and skill_md.exists() else ""):
        asset = None if _is_markdown(rel) else _read_linked_asset(root, rel)
        if asset:
            parts.append(_asset_block(rel, asset))

    if not parts:
        return None
    return f"## {name} (custom)\n\n" + "\n\n---\n\n".join(parts)


def fetch_skill(name: str, source: str) -> dict:
    """Download/copy a skill (see _fetch_skill_impl). A failed fetch leaves nothing behind:
    the skill folder is removed again unless it already existed before this call."""
    import shutil
    dest = USER_SKILLS / name.strip().replace(" ", "-").lower()
    existed = dest.exists()
    result = _fetch_skill_impl(name, source)
    if not result["ok"] and not existed:
        shutil.rmtree(dest, ignore_errors=True)
    return result


def remove_skill(name: str) -> bool:
    """Delete a downloaded skill folder from the user skills directory.

    Raises ValueError for names that would resolve outside that directory.
    Returns True if a folder was removed, False if there was nothing to remove.
    """
    import shutil
    slug = name.strip().replace(" ", "-").lower()
    skill_dir = (USER_SKILLS / slug).resolve()
    if not slug or skill_dir.parent != USER_SKILLS.resolve():
        raise ValueError(f"Invalid skill name: {name!r}")
    if not skill_dir.is_dir():
        return False
    shutil.rmtree(skill_dir)
    return True


def _fetch_skill_impl(name: str, source: str) -> dict:
    """
    Download or copy a skill into ~/.avio_skills/<name>/ and return a status dict.

    source can be:
      - "bundled:<slug>"             copy from SKILLS_DIR/<slug>
      - "https://..." or "http://..." fetch markdown files from a raw HTTP server
      - "file:///..." or "/abs/path"  copy from a local directory
      - "github:<slug>"              fetch from GH_RAW_BASE/<slug>

    Returns {"ok": bool, "path": str, "files": int, "error": str|None}
    """
    import shutil

    slug = name.strip().replace(" ", "-").lower()
    dest = USER_SKILLS / slug
    dest.mkdir(parents=True, exist_ok=True)

    files_written = 0

    try:
        # ── bundled sentinel ──────────────────────────────────────────────────
        if source.startswith("bundled:"):
            skill_slug = source[len("bundled:"):]
            src_dir = SKILLS_DIR / skill_slug
            if not src_dir.is_dir():
                return {"ok": False, "path": str(dest), "files": 0, "error": f"'{skill_slug}' is not bundled with this version of Avio yet"}
            files_written = _copy_skill_dir(src_dir, dest)

        # ── GitHub shorthand ──────────────────────────────────────────────────
        elif source.startswith("github:"):
            skill_slug = source[len("github:"):]
            base_url = f"{GH_RAW_BASE}/{skill_slug}"
            files_written = _fetch_skill_from_url(base_url, dest)

        # ── HTTP(S) URL ───────────────────────────────────────────────────────
        elif source.startswith("http://") or source.startswith("https://"):
            files_written = _fetch_skill_from_url(source.rstrip("/"), dest)

        # ── file:// or local path ─────────────────────────────────────────────
        else:
            raw = source[7:] if source.startswith("file://") else source
            src_dir = Path(raw).expanduser()
            if not src_dir.is_dir():
                return {"ok": False, "path": str(dest), "files": 0, "error": f"Directory not found: {src_dir}"}
            files_written = _copy_skill_dir(src_dir, dest)

        # Write a meta file so we know the origin
        (dest / ".avio_skill_meta.json").write_text(
            json.dumps({"name": name, "source": source, "fetched": str(Path(__file__).parent)}, indent=2)
        )

        if files_written == 0:
            return {"ok": False, "path": str(dest), "files": 0, "error": "No markdown files found at source"}

        log.info("sf_skills: fetched '%s' → %s (%d files)", name, dest, files_written)
        return {"ok": True, "path": str(dest), "files": files_written, "error": None}

    except Exception as e:
        log.error("sf_skills: fetch_skill failed for '%s': %s", name, e)
        return {"ok": False, "path": str(dest), "files": 0, "error": str(e)}


def _fetch_skill_from_url(base_url: str, dest: Path) -> int:
    """
    Fetch SKILL.md, every .md file it links to, and known reference file names
    from a raw HTTP base URL into dest/. Always downloads fresh (bypasses the
    cache). Returns number of files written.
    """
    written = 0

    def _save(rel: str, content: str) -> None:
        nonlocal written
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        written += 1

    skill_md = _load_file_url(base_url, "SKILL.md", use_cache=False)
    if skill_md:
        _save("SKILL.md", skill_md)
    for rel in _candidate_ref_paths(skill_md):
        content = _load_file_url(base_url, rel, use_cache=False)
        if content and (_is_markdown(rel) or len(content) <= _MAX_ASSET_CHARS):
            _save(rel, content)
    return written


def _copy_skill_dir(src_dir: Path, dest: Path) -> int:
    """Copy a skill folder: every markdown file, plus the non-markdown files SKILL.md links to
    (the same set _fetch_skill_from_url downloads). Returns the number of files copied."""
    import shutil
    copied = 0
    skill_md = src_dir / "SKILL.md"
    linked = _linked_paths(skill_md.read_text(encoding="utf-8")) if skill_md.is_file() else []
    wanted = list(src_dir.rglob("*.md")) + [
        src_dir / rel for rel in linked
        if not _is_markdown(rel) and _read_linked_asset(src_dir, rel) is not None
    ]
    for f in wanted:
        out = dest / f.relative_to(src_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        copied += 1
    return copied


# Added skills are only injected when they look relevant to the conversation, and the
# total is capped: injecting all of them cost ~80 KB (about 20k tokens) per message.
MAX_USER_SKILL_CHARS = 60_000

# Words in a skill's name that say nothing about its topic.
_NAME_STOPWORDS = {
    "platform", "generate", "create", "build", "skill", "skills", "salesforce", "sf",
    "best", "practice", "practices", "guide", "guidelines", "reference", "the", "and", "for",
}


def _skill_stems(*names: str) -> list[str]:
    """Topic stems from a skill's folder/display names: 'platform-apex-test-generate' -> ['apex', 'test']."""
    stems: list[str] = []
    for name in names:
        for tok in re.split(r"[^a-z0-9]+", (name or "").lower()):
            if len(tok) < 3 or tok in _NAME_STOPWORDS:
                continue
            stem = tok[:4] if len(tok) > 4 else tok   # 'testing' -> 'test', 'agentforce' -> 'agen'
            if stem not in stems:
                stems.append(stem)
    return stems


def _skill_score(stems: list[str], text: str) -> int:
    return sum(1 for s in stems if re.search(r"\b" + re.escape(s), text))


# The topic words of the built-in skills. Every Apex or SOQL prompt contains them (and the
# Apex/SOQL panels add them), so they cannot qualify a skill that also has a more specific
# topic word: 'apex-debug-logs' must not load for a test-class prompt just because both say apex.
_DOMAIN_STEMS = {"apex", "soql", "sosl"}


def _qualifies(stems: list[str], text: str) -> bool:
    """A skill is relevant when one of its specific topic words appears in the text; a skill
    named only with domain words (e.g. 'apex-guide') qualifies on those."""
    specific = [s for s in stems if s not in _DOMAIN_STEMS]
    return _skill_score(specific or stems, text) >= 1


def _build_user_skills_context(text: str = "", mode: str = "relevant",
                               max_chars: int = MAX_USER_SKILL_CHARS) -> str:
    """The context block only; see _user_skills for the selection rules."""
    return _user_skills(text, mode, max_chars)[0]


def _user_skills(text: str = "", mode: str = "relevant",
                 max_chars: int = MAX_USER_SKILL_CHARS) -> tuple[str, list[str]]:
    """
    Build the context block for skills in the user skills dir (added via Add Skill) and the
    display names of the skills that made it in.

    mode "relevant" (default): include a skill only if a specific topic word from its name
    appears in `text` (the recent conversation, plus 'apex'/'soql' when those built-in
    skills were detected); see _qualifies. A skill whose name has no topic words is always
    included. Best matches first, stopping at `max_chars` (default MAX_USER_SKILL_CHARS).
    mode "all": include every added skill (still capped).
    Returns ('', []) if nothing qualifies.
    """
    if not USER_SKILLS.is_dir():
        return "", []
    text = (text or "").lower()
    candidates: list[tuple[int, str, str]] = []   # (score, display, section)
    for skill_dir in sorted(USER_SKILLS.iterdir()):
        if not skill_dir.is_dir():
            continue
        # Read display name from meta
        display = skill_dir.name
        meta_file = skill_dir / ".avio_skill_meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                display = meta.get("name") or display
            except Exception:
                pass

        # Decide relevance before reading any files
        stems = _skill_stems(skill_dir.name, display)
        score = _skill_score(stems, text)           # used to rank; _qualifies decides inclusion
        if mode != "all" and stems and not _qualifies(stems, text):
            continue

        parts = []
        skill_text = ""
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            content = _load_file_local(skill_dir, "SKILL.md")
            if content:
                parts.append(content)
                skill_text = content
        for md in sorted(skill_dir.rglob("*.md")):
            if md == skill_md or md.name.startswith("."):
                continue
            try:
                content = md.read_text(encoding="utf-8")
                content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).strip()
                if content:
                    parts.append(content)
            except Exception:
                pass
        # Templates and samples the skill links to (assets/*.cls, ...): without them the model is
        # told to "start from the template" and never sees it.
        for rel in _linked_paths(skill_text):
            if _is_markdown(rel):
                continue
            asset = _read_linked_asset(skill_dir, rel)
            if asset:
                parts.append(_asset_block(rel, asset))
        if parts:
            candidates.append((score, display, f"## {display}\n\n" + "\n\n---\n\n".join(parts)))

    if not candidates:
        return "", []

    # Best matches first; stop adding once the budget is used up
    candidates.sort(key=lambda c: (-c[0], c[1].lower()))
    sections: list[str] = []
    names: list[str] = []
    used = 0
    skipped: list[str] = []
    for _score, display, section in candidates:
        if used + len(section) > max_chars:
            if sections:
                skipped.append(display)
                continue
            section = section[:max_chars] + "\n\n[... skill truncated ...]"
        sections.append(section)
        names.append(display)
        used += len(section)
    if skipped:
        log.warning("sf_skills: skipped added skills over the %d-char budget: %s", max_chars, skipped)

    return (
        "\n\n"
        "=== ADDITIONAL SKILL REFERENCE ===\n"
        "The following additional guidance has been added to Avio.\n\n"
        + "\n\n===\n\n".join(sections)
        + "\n\n=== END ADDITIONAL SKILL REFERENCE ==="
    ), names


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _condense(text: str, limit: int) -> str:
    """
    Shrink one skill file to about `limit` characters: drop the YAML header, start at the
    rules section if there is one (the most useful part), and cut at a heading or blank
    line so a rule is not split mid-sentence.
    """
    body = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL).lstrip()
    m = re.search(r"(?im)^##\s+[^\n]*(?:rules|constraints|guardrails)[^\n]*$", body)
    if m:
        body = body[m.start():]
    if len(body) <= limit:
        return body
    cut = body[:limit]
    idx = max(cut.rfind("\n### "), cut.rfind("\n## "), cut.rfind("\n\n"))
    if idx > limit * 0.5:
        cut = cut[:idx]
    return cut.rstrip() + "\n\n[... condensed for a small context window ...]"


def build_skill_context(skills: list[str], cfg: Optional[dict] = None,
                        budget: Optional[int] = None) -> str:
    """
    Assemble skill markdown for the given skill names into a single block
    ready to append to the system prompt. Returns "" if nothing available.

    `budget` (characters) switches to condensed mode for small-context models: only each
    skill's SKILL.md is used, shrunk with _condense, sharing the budget between skills.
    """
    if not skills:
        return ""

    if cfg is None:
        cfg = _load_skills_config()

    root     = _resolve_skills_root(cfg)
    use_http = (root is None)
    base_url = _effective_base_url(cfg) if use_http else ""

    per_skill = (budget // len(skills)) if budget is not None else 0
    sections: list[str] = []
    for skill in skills:
        files = SKILL_FILES.get(skill, [])
        if budget is not None:
            files = files[:1]   # SKILL.md only; reference files are too big for a small context
        parts = []
        for f in files:
            content = (
                _load_file_url(base_url, f) if use_http
                else _load_file_local(root, f)
            )
            if content and budget is not None:
                content = _condense(content, per_skill)
            if content:
                parts.append(content)
        if parts:
            sections.append(f"## {skill}\n\n" + "\n\n---\n\n".join(parts))

    if not sections:
        return ""

    return (
        "\n\n"
        "=== SALESFORCE SKILL REFERENCE (forcedotcom/sf-skills) ===\n"
        "The following official Salesforce guidance applies to this request. "
        "Follow these rules and patterns precisely.\n\n"
        + "\n\n===\n\n".join(sections)
        + "\n\n=== END SALESFORCE SKILL REFERENCE ==="
    )


def augment_system(system: Optional[str], messages: list[dict],
                   force_skills: Optional[list[str]] = None,
                   local: bool = False) -> str:
    """The augmented system prompt only; see augment_with_skills."""
    return augment_with_skills(system, messages, force_skills, local)[0]


def augment_with_skills(system: Optional[str], messages: list[dict],
                        force_skills: Optional[list[str]] = None,
                        local: bool = False) -> tuple[str, list[str]]:
    """
    Detect relevant skills from message history and append their context
    to the system prompt. Returns (system string, names of the skills actually injected),
    so the UI can show what was used instead of asking the model.
    `force_skills` are included regardless of keyword detection.
    `local=True` (Ollama and other local servers) switches to a condensed summary that
    fits a small context window; see LOCAL_SKILL_BUDGET / "skills_local_budget".
    Respects skills_enabled and skills_source config from the Avio config.json.
    """
    cfg = _load_skills_config()

    if not cfg.get("enabled", True):
        return system or "", []

    budget: Optional[int] = None
    if local:
        try:
            b = int(cfg.get("local_budget", LOCAL_SKILL_BUDGET))
        except (TypeError, ValueError):
            b = LOCAL_SKILL_BUDGET
        budget = None if b < 0 else b          # -1 = send everything, like a cloud model
        if budget == 0:
            return system or "", []            # skills switched off for local models

    skills = detect_skills(messages, force_skills)
    extra = build_skill_context(skills, cfg, budget=budget) if skills else ""
    names: list[str] = []
    if extra:
        log.info("sf_skills: injecting skills %s (source=%s%s)", skills, cfg.get("source"),
                 f", condensed to ~{budget} chars" if budget is not None else "")
        suffix = " (condensed)" if budget is not None else ""
        names = [f"{_SKILL_LABELS.get(s, s)}{suffix}" for s in skills]

    # Skills the user added: only the ones relevant to this conversation. The built-in
    # topics count as words in the conversation, so an added 'apex-test' skill is picked
    # up in the Apex Runner even when the prompt never says "apex".
    hints = (" apex" if APEX_SKILL in skills else "") + (" soql" if SOQL_SKILL in skills else "")
    if budget is None:
        user_cap = MAX_USER_SKILL_CHARS
    else:
        user_cap = max(0, budget - len(extra))   # whatever the built-in summary left over
    if user_cap >= 1500:
        user_ctx, user_names = _user_skills(
            _recent_user_text(messages) + hints, cfg.get("inject", "relevant"), max_chars=user_cap)
        if user_ctx:
            log.info("sf_skills: injecting added skills %s (%d chars)", user_names, len(user_ctx))
            extra += user_ctx
            names += user_names

    return ((system or "") + extra if extra else (system or "")), names


# ---------------------------------------------------------------------------
# Manifest — for /api/ai/skills endpoint
# ---------------------------------------------------------------------------

def get_skills_manifest(config_override: Optional[dict] = None) -> dict:
    """
    Return a dict describing bundled skills, config state, and version info.
    Used by the /api/ai/skills endpoint to power the Settings UI panel.
    Pass config_override to test a draft config without saving it first.
    """
    cfg = _load_skills_config()
    if config_override:
        cfg = {**cfg, **config_override}
    root = _resolve_skills_root(cfg)

    # Version info
    version_info = {}
    version_file = SKILLS_DIR / "VERSION"
    if version_file.exists():
        try:
            raw = version_file.read_text()
            kv: dict[str, str] = {}
            for line in raw.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    kv[k.strip()] = v.strip()
            upstream = kv.get("upstream-commit", "")
            parts = upstream.split()
            version_info = {
                "commit":  parts[0] if parts else "unknown",
                "date":    parts[1] if len(parts) > 1 else kv.get("fetched", ""),
                "source":  kv.get("source", ""),
                "fetched": kv.get("fetched", ""),
            }
        except Exception:
            version_info = {"commit": "unknown", "date": ""}

    # Build full catalog — bundled skills first, then upstream-only ones
    skills_status = []

    for skill_name in _UPSTREAM_CATALOG:
        is_bundled = skill_name in SKILL_FILES
        files      = SKILL_FILES.get(skill_name, [])

        if not is_bundled:
            # Not yet bundled — show in catalog as coming soon
            skills_status.append({
                "name":        skill_name,
                "label":       _SKILL_LABELS.get(skill_name, skill_name),
                "description": _SKILL_DESCS.get(skill_name, ""),
                "file_count":  0,
                "available":   False,
                "bundled":     False,
            })
            continue

        if cfg.get("source") in ("url", "github"):
            available  = True  # optimistic — can't probe without fetching
            file_count = len(files)
        elif root:
            file_count = sum(1 for f in files if (root / f).exists())
            available  = file_count > 0
        else:
            available  = False
            file_count = 0

        skills_status.append({
            "name":        skill_name,
            "label":       _SKILL_LABELS.get(skill_name, skill_name),
            "description": _SKILL_DESCS.get(skill_name, ""),
            "file_count":  file_count,
            "available":   available,
            "bundled":     True,
        })

    # Append skills from ~/.avio_skills/ — downloaded/imported by the user
    if USER_SKILLS.is_dir():
        for skill_dir in sorted(USER_SKILLS.iterdir()):
            if not skill_dir.is_dir():
                continue
            # Read meta if present for display name
            meta = {}
            meta_file = skill_dir / ".avio_skill_meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                except Exception:
                    pass
            skill_md   = skill_dir / "SKILL.md"
            file_count = sum(1 for f in skill_dir.rglob("*.md") if not f.name.startswith("."))
            if file_count == 0:
                continue   # empty leftover from a failed download: don't list it
            available  = skill_md.exists() and file_count > 0
            display    = meta.get("name") or skill_dir.name
            source_url = meta.get("source", "")
            skills_status.append({
                "name":        skill_dir.name,
                "label":       display,
                "description": source_url or str(skill_dir),
                "file_count":  file_count,
                "available":   available,
                "bundled":     True,
                "user":        True,   # downloaded by user, not shipped with app
            })

    source = cfg.get("source", "bundled")
    return {
        "enabled":     cfg.get("enabled", True),
        "source":      source,
        "skills_path": cfg.get("path") or "",
        "skills_url":  cfg.get("url") or (GH_RAW_BASE if source == "github" else ""),
        "version":     version_info,
        "skills":      skills_status,
    }


_SKILL_LABELS = {
    "platform-soql-query":            "SOQL Query",
    "platform-apex-generate":         "Apex Generate",
    "platform-apex-logs-debug":       "Apex Debug Logs",
    "platform-apex-test-generate":    "Apex Test Generate",
    "automation-flow-generate":       "Flow Generate",
    "experience-lwc-generate":        "LWC Generate",
    "platform-metadata-retrieve":     "Metadata Retrieve",
    "platform-metadata-deploy":       "Metadata Deploy",
    "platform-permission-set-generate": "Permission Set Generate",
}

_SKILL_DESCS = {
    "platform-soql-query":            "SOQL authoring, optimization, anti-patterns, and reference",
    "platform-apex-generate":         "Apex class and trigger generation, best practices",
    "platform-apex-logs-debug":       "Debug log analysis, governor limits, and stack-trace troubleshooting",
    "platform-apex-test-generate":    "Apex test classes: TestDataFactory, bulk (251+ records), mocking, assertions",
    "automation-flow-generate":       "Flow generation: Screen, Autolaunched, Record-Triggered, and Scheduled flows",
    "experience-lwc-generate":        "Lightning Web Components (PICKLES), wire patterns, and Jest tests",
    "platform-metadata-retrieve":     "Retrieve metadata with sf project retrieve start (by type, manifest, or package)",
    "platform-metadata-deploy":       "Deploy, validate, and quick-deploy metadata with sf CLI v2",
    "platform-permission-set-generate": "Permission set metadata (PermissionSet XML): object, field, user, and app permissions",
}

# Skills in the upstream repo (forcedotcom/sf-skills, skills/<slug>/) not yet bundled,
# shown in the UI as coming soon. Every slug here must exist upstream.
_UPSTREAM_CATALOG = [
    "platform-soql-query",             # bundled
    "platform-apex-generate",          # bundled
    "platform-apex-logs-debug",
    "platform-apex-test-generate",
    "automation-flow-generate",
    "experience-lwc-generate",
    "platform-metadata-retrieve",
    "platform-metadata-deploy",
    "platform-permission-set-generate",
]
