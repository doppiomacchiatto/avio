"""
Saved AI conversations.

When the user closes Avio and chooses to keep an AI conversation, it is written here, in the
app-data folder, so the panel can offer to restore it on the next launch. Nothing is saved
unless the user asks for it, and a saved conversation is deleted after RETENTION_DAYS.

Chats are plain text on disk (protected only by the OS user's file permissions) and can hold
Salesforce code and data. No connection, URL or key is ever stored with them.

Layout: <avio data dir>/chats/<id>.json, id = <surface>-YYYYMMDD-HHMMSS[-n]. Ids are generated
here and validated against _ID_RE, so a request can never name a path.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from platform_env import avio_data_dir

log = logging.getLogger(__name__)

FORMAT_VERSION  = 1
RETENTION_DAYS  = 3
SURFACES        = ("apex", "soql", "chat", "fls", "profiles", "rest")
MAX_MESSAGES    = 500                 # per conversation; the oldest are dropped past this
MAX_CHARS       = 2_000_000           # total message text per conversation; the oldest are dropped past this
MAX_FILES       = 60                  # safety net on top of the age limit
_MAX_SKILLS     = 20
_MAX_SKILL_LEN  = 100

_ID_RE = re.compile(r"^(apex|soql|chat|fls|profiles|rest)-\d{8}-\d{6}(-\d+)?$")


class InvalidChat(ValueError):
    """The request cannot be saved (bad surface, nothing to save...)."""


class UnknownChat(KeyError):
    """No saved conversation has that id (never saved, deleted, or expired)."""


def chats_dir() -> Path:
    d = avio_data_dir() / "chats"
    d.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
    return d


def valid_id(chat_id: object) -> bool:
    return isinstance(chat_id, str) and bool(_ID_RE.fullmatch(chat_id))   # fullmatch: "$" accepts a trailing newline


def _path(chat_id: str) -> Path:
    if not valid_id(chat_id):
        raise UnknownChat(chat_id)
    return chats_dir() / f"{chat_id}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def clean_messages(messages: object) -> list[dict]:
    """Keep only what a conversation needs: user/assistant text and the skills a reply used.

    UI notices (`system: true`), unknown roles, non-string or empty content and unknown fields
    are dropped, so a stored file cannot carry anything the app does not understand.
    """
    out: list[dict] = []
    if not isinstance(messages, list):
        return out
    for m in messages:
        if not isinstance(m, dict) or m.get("system") is True:
            continue
        role, content = m.get("role"), m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        item = {"role": role, "content": content}
        skills = m.get("skills")
        if role == "assistant" and isinstance(skills, list):
            names = [s[:_MAX_SKILL_LEN] for s in skills if isinstance(s, str) and s.strip()][:_MAX_SKILLS]
            if names:
                item["skills"] = names
        out.append(item)
    return out


def _fit(messages: list[dict]) -> tuple[list[dict], int]:
    """Drop the oldest messages until the conversation fits the caps. Returns (kept, dropped)."""
    kept = messages[-MAX_MESSAGES:]
    total = sum(len(m["content"]) for m in kept)
    while kept and total > MAX_CHARS:
        total -= len(kept[0]["content"])
        kept = kept[1:]
    return kept, len(messages) - len(kept)


def _title(messages: list[dict], given: Optional[str]) -> str:
    text = (given or "").strip()
    if not text:
        first = next((m["content"] for m in messages if m["role"] == "user"), "")
        text = first
    text = " ".join(text.split())
    return text[:60] + ("..." if len(text) > 60 else "")


def _saved_at(data: dict, path: Path) -> datetime:
    try:
        when = datetime.fromisoformat(str(data.get("saved_at", "")).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _read(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("avio_chat") != FORMAT_VERSION:
        return None
    return data


def purge_expired(now: Optional[datetime] = None) -> int:
    """Delete saved conversations older than RETENTION_DAYS (and unreadable files), then trim
    to MAX_FILES, oldest first. Returns how many were deleted."""
    now = now or _now()
    limit = now - timedelta(days=RETENTION_DAYS)
    removed = 0
    alive: list[tuple[datetime, Path]] = []
    for p in chats_dir().glob("*.json"):
        data = _read(p) if valid_id(p.stem) else None
        when = _saved_at(data, p) if data else None
        if when is None or when < limit:
            try:
                p.unlink()
                removed += 1
            except OSError as e:
                log.warning("Could not delete expired chat %s: %s", p.name, type(e).__name__)
        else:
            alive.append((when, p))
    alive.sort(key=lambda t: t[0])
    while len(alive) > MAX_FILES:
        _, p = alive.pop(0)
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    # leftovers of an interrupted write
    for p in chats_dir().glob("*.tmp"):
        try:
            p.unlink()
        except OSError:
            pass
    return removed


def _summary(data: dict, chat_id: str, when: datetime) -> dict:
    expires = when + timedelta(days=RETENTION_DAYS)
    return {
        "id": chat_id,
        "surface": data.get("surface"),
        "saved_at": when.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "count": len(data.get("messages", [])),
        "title": data.get("title", ""),
    }


def list_chats(surface: Optional[str] = None, now: Optional[datetime] = None) -> list[dict]:
    """Saved conversations, newest first. Expired ones are deleted first."""
    if surface is not None and surface not in SURFACES:
        raise InvalidChat("Unknown surface.")
    purge_expired(now)
    items = []
    for p in chats_dir().glob("*.json"):
        data = _read(p)
        if not data or not valid_id(p.stem):
            continue
        if surface and data.get("surface") != surface:
            continue
        items.append(_summary(data, p.stem, _saved_at(data, p)))
    items.sort(key=lambda s: (s["saved_at"], s["id"]), reverse=True)
    return items


def get_chat(chat_id: str, now: Optional[datetime] = None) -> dict:
    purge_expired(now)
    path = _path(chat_id)
    data = _read(path) if path.exists() else None
    if not data:
        raise UnknownChat(chat_id)
    return {**_summary(data, chat_id, _saved_at(data, path)), "messages": data.get("messages", [])}


def _new_id(surface: str, now: datetime) -> str:
    base = f"{surface}-{now.strftime('%Y%m%d-%H%M%S')}"
    d = chats_dir()
    chat_id, n = base, 1
    while (d / f"{chat_id}.json").exists():
        n += 1
        chat_id = f"{base}-{n}"
    return chat_id


def save_chat(surface: str, messages: object, title: Optional[str] = None,
              now: Optional[datetime] = None) -> dict:
    """Store a conversation. Returns its summary plus `dropped` (oldest messages that did not fit)."""
    if surface not in SURFACES:
        raise InvalidChat("Unknown surface.")
    now = (now or _now()).replace(microsecond=0)
    kept, dropped = _fit(clean_messages(messages))
    if not kept:
        raise InvalidChat("There is nothing to save: the conversation has no messages.")
    purge_expired(now)
    chat_id = _new_id(surface, now)
    data = {
        "avio_chat": FORMAT_VERSION,
        "id": chat_id,
        "surface": surface,
        "saved_at": now.isoformat().replace("+00:00", "Z"),
        "title": _title(kept, title),
        "messages": kept,
    }
    d = chats_dir()
    fd, tmp = tempfile.mkstemp(prefix=".chat-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, d / f"{chat_id}.json")
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    purge_expired(now)          # also enforces MAX_FILES now that this one exists
    return {**_summary(data, chat_id, now), "dropped": dropped}


def delete_chat(chat_id: str) -> None:
    path = _path(chat_id)
    try:
        path.unlink()
    except FileNotFoundError:
        raise UnknownChat(chat_id)


def delete_all() -> int:
    removed = 0
    for p in chats_dir().glob("*.json"):
        if valid_id(p.stem):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed
