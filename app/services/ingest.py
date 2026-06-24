"""Ingest — idempotent batch upsert keyed on ``event_id``.

Each record is validated against the gates (identity ownership, consent already granted
at registration, mod flag, version presence). Re-uploading the same ``event_id`` converges
to a single stored row (SERVICE.md §8.3): we look up existing IDs and skip re-inserting
them, reporting them as accepted so the client can prune. A modded record is rejected.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Identity, Run
from app.schemas import IngestResponse, RunRecord


def ingest_records(
    db: Session, caller: Identity, records: list[RunRecord]
) -> IngestResponse:
    accepted: list[str] = []
    rejected: list[dict[str, str]] = []

    # which of these event_ids already exist? (idempotency)
    incoming_ids = [r.event_id for r in records]
    existing = set(
        db.execute(select(Run.event_id).where(Run.event_id.in_(incoming_ids)))
        .scalars()
        .all()
    )

    seen_in_batch: set[str] = set()

    for rec in records:
        # --- gates -----------------------------------------------------------
        if rec.integrity.modded:
            rejected.append({"eventId": rec.event_id, "reason": "modded"})
            continue
        if rec.fingerprint != caller.fingerprint:
            rejected.append({"eventId": rec.event_id, "reason": "fingerprint-mismatch"})
            continue
        if not rec.ruleset_version or not rec.content_version:
            rejected.append({"eventId": rec.event_id, "reason": "missing-version"})
            continue

        # --- idempotency -----------------------------------------------------
        # already stored, or a duplicate within this same batch → accept, don't re-insert
        if rec.event_id in existing or rec.event_id in seen_in_batch:
            accepted.append(rec.event_id)
            continue

        db.add(_to_row(rec))
        seen_in_batch.add(rec.event_id)
        accepted.append(rec.event_id)

    db.commit()
    return IngestResponse(accepted=accepted, rejected=rejected)


def _to_row(rec: RunRecord) -> Run:
    return Run(
        event_id=rec.event_id,
        fingerprint=rec.fingerprint,
        schema_version=rec.schema_version,
        ruleset_version=rec.ruleset_version,
        content_version=rec.content_version,
        modded=rec.integrity.modded,
        manifest_hash=rec.integrity.manifest_hash,
        kind=rec.context.kind,
        daily_date=rec.context.daily_date,
        class_id=rec.context.class_id,
        foe_id=rec.context.foe_id,
        seed=rec.context.seed,
        spec_ref=rec.context.spec_ref,
        result=rec.outcome.result,
        terms=rec.outcome.terms,
        real_time_ms=rec.outcome.real_time_ms,
        depth_reached=rec.outcome.depth_reached,
        actions=rec.actions,
        instruments=rec.instruments,
    )
