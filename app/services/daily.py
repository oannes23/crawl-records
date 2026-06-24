"""Daily challenge — a pure deterministic function of date (+ active versions).

The seed derivation is a stable hash over ``date | ruleset_version | content_version``,
so the same date on the same versions always yields the identical descriptor (SERVICE.md
§8.8). The UTC calendar date is the rollover boundary. The descriptor references only
content that already exists in the client; no content ships.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.config import Settings
from app.schemas import DailyDescriptor

# MVP criteria (SERVICE.md §6/§8.7). Order is stable.
DAILY_CRITERIA = ["fewest-terms", "fastest-clear", "deepest-delve"]


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seed_for(date: str, ruleset_version: str, content_version: str) -> str:
    payload = f"{date}|{ruleset_version}|{content_version}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


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
    )


def validate_date(date: str) -> str:
    """Accept an explicit ``YYYY-MM-DD`` or default to today (UTC). Raises ValueError."""
    if not date:
        return today_utc()
    # strict parse; rejects malformed input
    datetime.strptime(date, "%Y-%m-%d")
    return date
