"""The ``run`` table — one row per uploaded run record.

``event_id`` is the idempotency key (client-generated UUID): re-uploading the same
``event_id`` upserts, never double-counts. The columns I slice bests on (context + outcome)
are broken out as real columns; everything the MVP never interprets — ``actions`` (the
replay-ready ordered decision log) and ``instruments`` (the open dev-stat summary) — is
stored as opaque JSON, append-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class Run(Base):
    __tablename__ = "run"

    # --- idempotency + identity ---------------------------------------------
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # --- versioning (asserted on every record; opaque tokens) ---------------
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content_version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # --- integrity (mod gate; hash slot reserved for the future manifest) ---
    modded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manifest_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- context (sliced for bests) -----------------------------------------
    kind: Mapped[str] = mapped_column(String(16), index=True, nullable=False)  # delve | daily
    daily_date: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    class_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    foe_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    seed: Mapped[str] = mapped_column(String(128), nullable=False)
    spec_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    # --- outcome (the numbers bests are computed from) ----------------------
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # win | loss | flee
    terms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    real_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth_reached: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- opaque payloads (never parsed by the MVP) --------------------------
    actions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    instruments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
