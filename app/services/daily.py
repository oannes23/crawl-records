"""Daily challenge — a pure deterministic function of date (+ active versions).

The seed derivation is a stable hash over ``date | ruleset_version | content_version``,
so the same date on the same versions always yields the identical descriptor (SERVICE.md
§8.8). The UTC calendar date is the rollover boundary. The descriptor references only
content that already exists in the client; no content ships.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.config import Settings
from app.schemas import DailyDescriptor, DailySpec

# MVP criteria (SERVICE.md §6/§8.7). Order is stable.
DAILY_CRITERIA = ["fewest-terms", "fastest-clear", "deepest-delve"]


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seed_for(date: str, ruleset_version: str, content_version: str) -> str:
    payload = f"{date}|{ruleset_version}|{content_version}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


@lru_cache(maxsize=8)
def _load_daily_file(path: str, mtime: float) -> dict:
    """Load + cache the authored-daily JSON. ``mtime`` is part of the cache key so edits to
    the file invalidate the cache without a restart."""
    return json.loads(Path(path).read_text())


def authored_spec(date: str, settings: Settings) -> DailySpec | None:
    """Return the authored spec for ``date`` if the operator configured one (path b), else
    None (path a — the client derives selections from the seed). Stays deterministic: the
    file is static, so the same date yields the same spec."""
    if not settings.daily_file:
        return None
    p = Path(settings.daily_file)
    if not p.exists():
        return None
    table = _load_daily_file(str(p), p.stat().st_mtime)
    entry = table.get(date)
    return DailySpec(**entry) if entry else None


def daily_descriptor(date: str, settings: Settings) -> DailyDescriptor:
    seed = _seed_for(date, settings.ruleset_version, settings.content_version)
    # spec_ref is a deterministic, date-addressable handle the client regenerates from.
    spec_ref = f"daily/{date}/{settings.ruleset_version}+{settings.content_version}"
    return DailyDescriptor(
        date=date,
        seed=seed,
        spec_ref=spec_ref,
        ruleset_version=settings.ruleset_version,
        content_version=settings.content_version,
        criteria=list(DAILY_CRITERIA),
        spec=authored_spec(date, settings),
    )


def validate_date(date: str) -> str:
    """Accept an explicit ``YYYY-MM-DD`` or default to today (UTC). Raises ValueError.

    Returns the **normalized** (zero-padded) form: ``strptime`` accepts non-padded input
    like ``2026-7-1``, and the raw string is hashed into the seed and used as the bests
    daily-slice key — so without normalization ``2026-7-1`` and ``2026-07-01`` would yield
    different boards and split the same calendar day into two slices (FABLE B3).
    """
    if not date:
        return today_utc()
    # strict parse (rejects malformed input) + re-emit zero-padded canonical form
    return datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
