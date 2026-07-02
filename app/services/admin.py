"""Admin query helpers — read-only views over the corpus for the admin panel.

These power the admin UI and its thin JSON layer. They reuse the same models as the
public API; no query logic is duplicated across the two surfaces.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.models import Identity, Run


def list_runs(
    db: Session,
    *,
    fingerprint: str | None = None,
    handle: str | None = None,
    class_id: str | None = None,
    foe_id: str | None = None,
    kind: str | None = None,
    result: str | None = None,
    ruleset_version: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "created_at",
    desc: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Run], int]:
    stmt = select(Run)

    if handle:
        # resolve handle → fingerprint(s)
        fps = (
            db.execute(
                select(Identity.fingerprint).where(Identity.handle_lower == handle.lower())
            )
            .scalars()
            .all()
        )
        # no fingerprint matched the handle → match nothing (portable, no magic sentinel)
        stmt = stmt.where(Run.fingerprint.in_(fps) if fps else false())
    if fingerprint:
        stmt = stmt.where(Run.fingerprint == fingerprint)
    if class_id:
        stmt = stmt.where(Run.class_id == class_id)
    if foe_id:
        stmt = stmt.where(Run.foe_id == foe_id)
    if kind:
        stmt = stmt.where(Run.kind == kind)
    if result:
        stmt = stmt.where(Run.result == result)
    if ruleset_version:
        stmt = stmt.where(Run.ruleset_version == ruleset_version)
    if date_from:
        stmt = stmt.where(Run.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Run.created_at <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    sort_col = {
        "created_at": Run.created_at,
        "terms": Run.terms,
        "real_time_ms": Run.real_time_ms,
        "depth_reached": Run.depth_reached,
        "class_id": Run.class_id,
        "foe_id": Run.foe_id,
    }.get(sort, Run.created_at)
    stmt = stmt.order_by(sort_col.desc() if desc else sort_col.asc())
    stmt = stmt.limit(limit).offset(offset)

    rows = db.execute(stmt).scalars().all()
    return rows, total


def get_run(db: Session, event_id: str) -> Run | None:
    return db.get(Run, event_id)


def list_identities(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(Identity).order_by(Identity.created_at.desc())).scalars().all()
    counts = dict(
        db.execute(select(Run.fingerprint, func.count()).group_by(Run.fingerprint)).all()
    )
    return [
        {
            "handle": i.handle,
            "fingerprint": i.fingerprint,
            "consent_version": i.consent_version,
            "consent_at": i.consent_at.isoformat() if i.consent_at else None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "runs": counts.get(i.fingerprint, 0),
        }
        for i in rows
    ]


def instrument_aggregates(db: Session) -> dict[str, Any]:
    """Aggregate the TUNING.md dev-instrument targets across the corpus.

    Instruments are an open JSON blob; we pull the documented numeric keys when present
    and average them. Targets (TUNING.md §"Dev-instrument design targets"):
    reshape share 65-70% · trap-spring rate ~30% · sets/round ~3 (4-6 competent).
    """
    runs = db.execute(select(Run.instruments)).scalars().all()
    keys = ("reshareSharePlayer", "trapSpringRate", "setsPerRound", "setsMatched")
    sums: dict[str, float] = {k: 0.0 for k in keys}
    n: dict[str, int] = {k: 0 for k in keys}
    for blob in runs:
        if not isinstance(blob, dict):
            continue
        for k in keys:
            v = blob.get(k)
            if isinstance(v, (int, float)):
                sums[k] += v
                n[k] += 1
    return {
        "total_runs": len(runs),
        "averages": {k: (sums[k] / n[k] if n[k] else None) for k in keys},
        "counts": n,
        "targets": {
            "reshareSharePlayer": "0.65-0.70",
            "trapSpringRate": "~0.30",
            "setsPerRound": "~3 (4-6 competent)",
        },
    }
