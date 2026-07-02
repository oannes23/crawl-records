"""Ingest — idempotent, first-write-wins batch insert keyed on ``event_id``.

Each record is validated against the gates (identity ownership, consent already granted
at registration, mod flag, version presence). Re-uploading the same ``event_id`` by the
same owner converges to the single stored row (SERVICE.md §8.3): we look up the caller's
existing IDs and skip re-inserting them, reporting them accepted so the client can prune.
Records are immutable events — a re-sent ``event_id`` with different content keeps the
first-written row (this is insert-or-skip, not update). A modded record is rejected.

Idempotency is scoped to the caller: an ``event_id`` that already exists under a *different*
identity is a conflict, not a duplicate — accepting it silently would let the client prune a
run that was never stored (FABLE B1). Such records are rejected ``event-id-conflict``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Identity, Run
from app.schemas import IngestResponse, RejectedRecord, RunRecord

# Every MVP reject is permanent: the client should quarantine/drop these, not retry
# (SERVICE-REPLY.md item 4). A future retryable reason would be emitted with terminal=False.
_TERMINAL_REASONS = (
    "modded",
    "fingerprint-mismatch",
    "missing-version",
    "event-id-conflict",
)


def ingest_records(
    db: Session, caller: Identity, records: list[RunRecord]
) -> IngestResponse:
    accepted: list[str] = []
    rejected: list[RejectedRecord] = []

    def reject(event_id: str, reason: str) -> None:
        rejected.append(RejectedRecord(event_id=event_id, reason=reason, terminal=True))

    # which of these event_ids already exist, and under whose fingerprint? (idempotency +
    # cross-owner conflict detection)
    incoming_ids = [r.event_id for r in records]
    owner_by_id: dict[str, str] = dict(
        db.execute(
            select(Run.event_id, Run.fingerprint).where(Run.event_id.in_(incoming_ids))
        ).all()
    )

    seen_in_batch: set[str] = set()

    for rec in records:
        # --- gates -----------------------------------------------------------
        if rec.integrity.modded:
            reject(rec.event_id, "modded")
            continue
        if rec.fingerprint != caller.fingerprint:
            reject(rec.event_id, "fingerprint-mismatch")
            continue
        if not rec.ruleset_version or not rec.content_version:
            reject(rec.event_id, "missing-version")
            continue

        # --- idempotency (caller-scoped) -------------------------------------
        prior_owner = owner_by_id.get(rec.event_id)
        if prior_owner is not None and prior_owner != caller.fingerprint:
            # the id is already owned by someone else — never claim it accepted
            reject(rec.event_id, "event-id-conflict")
            continue
        # already stored by this caller, or a duplicate within this same batch → accept,
        # don't re-insert
        if prior_owner == caller.fingerprint or rec.event_id in seen_in_batch:
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
