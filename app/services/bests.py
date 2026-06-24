"""Personal bests — server-computed, compute-on-read (MVP).

Single-player volume is tiny, so we load the caller's runs and reduce in Python rather
than relying on dialect-specific SQL (``DISTINCT ON`` / window functions differ across
SQLite and Postgres — this keeps the MVP portable per SERVICE.md §8.1). The seam to
materialize a ``bests`` read model later is clean: replace ``compute_bests`` internals.

Criteria (SERVICE.md §8.7), sliced per (class × foe), with a daily slice keyed by date:
- ``fewest-terms``   — min ``terms`` over winning clears
- ``fastest-clear``  — min ``real_time_ms`` over winning clears
- ``deepest-delve``  — max ``depth_reached`` over all runs (depth counts even on a loss)

Tie-break (deterministic, documented): better raw value wins; on an exact tie, the
**earliest** ``created_at`` wins; on a further tie, the lexically smallest ``event_id``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Run
from app.schemas import BestEntry, BestsResponse


@dataclass(frozen=True)
class _Criterion:
    name: str
    field: str
    maximize: bool
    require_win: bool


_CRITERIA = (
    _Criterion("fewest-terms", "terms", maximize=False, require_win=True),
    _Criterion("fastest-clear", "real_time_ms", maximize=False, require_win=True),
    _Criterion("deepest-delve", "depth_reached", maximize=True, require_win=False),
)


def _is_better(candidate: Run, current: Run, crit: _Criterion) -> bool:
    cv = getattr(candidate, crit.field)
    ov = getattr(current, crit.field)
    if cv != ov:
        return cv > ov if crit.maximize else cv < ov
    # tie on value → earliest achievement
    if candidate.created_at != current.created_at:
        return candidate.created_at < current.created_at
    # final tie → lexically smallest event_id
    return candidate.event_id < current.event_id


def compute_bests(db: Session, fingerprint: str) -> BestsResponse:
    runs = db.execute(select(Run).where(Run.fingerprint == fingerprint)).scalars().all()

    # key = (criterion, class_id, foe_id, daily_date) → best Run so far
    best: dict[tuple, Run] = {}

    for run in runs:
        if run.modded:
            continue
        for crit in _CRITERIA:
            if getattr(run, crit.field) is None:
                continue
            if crit.require_win and run.result != "win":
                continue
            # daily runs slice by date; delve runs carry daily_date=None
            daily_date = run.daily_date if run.kind == "daily" else None
            key = (crit.name, run.class_id, run.foe_id, daily_date)
            incumbent = best.get(key)
            if incumbent is None or _is_better(run, incumbent, crit):
                best[key] = run

    entries: list[BestEntry] = []
    for (criterion, class_id, foe_id, daily_date), run in best.items():
        entries.append(
            BestEntry(
                criterion=criterion,
                class_id=class_id,
                foe_id=foe_id,
                daily_date=daily_date,
                value=getattr(run, _field_for(criterion)),
                event_id=run.event_id,
                achieved_at=run.created_at.isoformat(),
            )
        )

    # stable ordering for deterministic responses + readable admin output
    entries.sort(key=lambda e: (e.criterion, e.class_id, e.foe_id or "", e.daily_date or ""))
    return BestsResponse(bests=entries)


def _field_for(criterion: str) -> str:
    for c in _CRITERIA:
        if c.name == criterion:
            return c.field
    raise KeyError(criterion)
