"""Auth — two separate, minimal schemes.

1. Player bearer token: an opaque random token issued at registration, bound to the
   fingerprint. Required on write/``/me`` endpoints. No rotation in the MVP (documented
   open question). Validated by lookup against the ``identity`` table.
2. Admin HTTP Basic: gates the ``/admin`` panel only, credentials from config. Entirely
   separate from player tokens.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Identity

# --- token + recovery-code helpers ------------------------------------------

_RECOVERY_WORDS = (
    "amber ash birch cinder delve ember frost glint hearth ivory jasper kiln "
    "lumen moss nimbus onyx pyre quill rune sable thorn umber vault warden yarrow zephyr"
).split()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_recovery_code() -> str:
    """A human-transcribable four-word code (e.g. ``amber-thorn-rune-kiln``)."""
    return "-".join(secrets.choice(_RECOVERY_WORDS) for _ in range(4))


def hash_recovery_code(code: str) -> str:
    """Recovery codes are stored hashed (SERVICE.md §8.5)."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_recovery_code(code: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_recovery_code(code), stored_hash)


# --- player bearer dependency -----------------------------------------------

# auto_error=False so a MISSING Authorization header returns 401 (with a WWW-Authenticate
# challenge) rather than HTTPBearer's default 403 — a missing credential is "unauthenticated",
# not "forbidden" (FABLE C5).
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "missing or invalid bearer token",
    headers={"WWW-Authenticate": "Bearer"},
)


def require_identity(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Identity:
    """Resolve the caller's identity from the bearer token, or 401."""
    if creds is None:
        raise _UNAUTHENTICATED
    identity = db.execute(
        select(Identity).where(Identity.token == creds.credentials)
    ).scalar_one_or_none()
    if identity is None:
        raise _UNAUTHENTICATED
    return identity


# --- admin Basic dependency -------------------------------------------------

_basic = HTTPBasic(auto_error=True)


def require_admin(creds: HTTPBasicCredentials = Depends(_basic)) -> str:
    settings = get_settings()
    ok_user = secrets.compare_digest(creds.username, settings.admin_user)
    ok_pass = secrets.compare_digest(creds.password, settings.admin_password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username
