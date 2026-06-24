"""The ``identity`` table — fingerprint + unique handle + recovery code + token.

Identity is two-part (SERVICE.md §2):
- ``fingerprint`` — a client-generated UUID, the anonymous stable server key.
- ``handle`` — globally unique, first-come claimed.
A ``recovery_code`` (stored hashed) lets a new install re-bind a fresh fingerprint.
The bearer ``token`` is bound to the fingerprint and authenticates write/``/me`` calls.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Identity(Base):
    __tablename__ = "identity"

    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    # handle_lower carries the uniqueness constraint (case-insensitive first-come claim);
    # handle preserves the player's chosen casing for display.
    handle: Mapped[str] = mapped_column(String(64), nullable=False)
    handle_lower: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    recovery_code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)

    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
