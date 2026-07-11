"""Encrypt/decrypt server SSH passwords in DB (Fernet, key derived from session_secret)."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

log = logging.getLogger(__name__)


def _fernet() -> Fernet:
    raw = hashlib.sha256((get_settings().session_secret + "vpn-bot-ssh-v1").encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_ssh_password(plain: str | None) -> str | None:
    s = (plain or "").strip()
    if not s:
        return None
    return _fernet().encrypt(s.encode()).decode()


def decrypt_ssh_password(stored: str | None) -> str | None:
    if not (stored or "").strip():
        return None

    value = stored.strip()

    try:
        return _fernet().decrypt(value.encode()).decode()

    except InvalidToken:
        log.warning("ssh_secret: value is not encrypted, using plaintext (re-encryption recommended)")
        return value

    except Exception:
        log.exception("ssh_secret: unexpected error during decryption")
        return None
