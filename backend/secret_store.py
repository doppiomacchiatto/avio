"""
secret_store.py — where Avio keeps API keys.

Keys go in the operating system's keystore through the `keyring` library:

  Windows  Credential Manager
  macOS    Keychain
  Linux    Secret Service (gnome-keyring, KWallet, ...)

If no usable keystore exists (a headless Linux box, or the keystore refuses the value,
e.g. Windows caps a credential at about 1,280 characters) the key is written to a private
file in the Avio data dir instead and callers can tell: set() returns "file" and status()
reports secure=False so the UI can warn.

Secrets are never logged and never returned by any HTTP endpoint.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

from platform_env import avio_data_dir

log = logging.getLogger(__name__)

SERVICE = "Avio"
FORCE_FILE_ENV = "AVIO_SECRET_BACKEND"   # "file" forces the file fallback (tests, headless setups)


def _keyring():
    """The keyring module if a real, working backend exists, else None."""
    if os.environ.get(FORCE_FILE_ENV, "").strip().lower() == "file":
        return None
    try:
        import keyring
        kr = keyring.get_keyring()
        # fail.Keyring has priority 0 and the null backend -1: both would lose the secret.
        if kr.priority < 1:
            return None
        return keyring
    except Exception as e:                       # no keyring package, or no viable backend
        log.info("secret_store: no usable keystore (%s)", type(e).__name__)
        return None


def _fallback_dir(create: bool = False) -> Path:
    d = avio_data_dir() / "secrets"
    if create:                      # only when a secret is actually written there
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            os.chmod(d, 0o700)
    return d


def _fallback_path(account: str, create: bool = False) -> Path:
    return _fallback_dir(create) / (re.sub(r"[^A-Za-z0-9._-]", "_", account) + ".key")


def _file_get(account: str) -> Optional[str]:
    p = _fallback_path(account)
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _file_set(account: str, value: str) -> None:
    p = _fallback_path(account, create=True)
    p.write_text(value, encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(p, 0o600)


def _file_delete(account: str) -> None:
    try:
        _fallback_path(account).unlink()
    except OSError:
        pass


def status() -> dict:
    """{"kind": "keystore"|"file", "label": human-readable, "secure": bool}"""
    if _keyring() is not None:
        if sys.platform == "win32":
            label = "Windows Credential Manager"
        elif sys.platform == "darwin":
            label = "macOS Keychain"
        else:
            label = "your system keyring (Secret Service)"
        return {"kind": "keystore", "label": label, "secure": True}
    return {"kind": "file", "label": "a file in your Avio data folder (not encrypted)", "secure": False}


def get(account: str) -> Optional[str]:
    kr = _keyring()
    if kr is not None:
        try:
            value = kr.get_password(SERVICE, account)
            if value:
                return value
        except Exception as e:
            log.warning("secret_store: keystore read failed (%s)", type(e).__name__)
    return _file_get(account)    # also finds values saved while no keystore was available


def set(account: str, value: str) -> str:
    """Store a secret. Returns "keystore" or "file" (where it actually went)."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, account, value)
            if kr.get_password(SERVICE, account) == value:   # some backends fail silently
                _file_delete(account)                        # no stale plaintext copy
                return "keystore"
            log.warning("secret_store: keystore did not return the stored value; using the file fallback")
        except Exception as e:
            log.warning("secret_store: keystore write failed (%s); using the file fallback", type(e).__name__)
    _file_set(account, value)
    return "file"


def delete(account: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, account)
        except Exception:
            pass                                             # nothing stored there
    _file_delete(account)
