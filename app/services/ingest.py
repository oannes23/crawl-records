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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Identity, Run
from app.schemas import IngestResponse, RejectedRecord, RunRecord

# Every MVP reject is permanent: the client should quarantine/drop these, not retry
# (SERVICE-REPLY.md item 4). A future retryable reason would be emitted with terminal=False.
_TERMINAL_REASONS = (
    "modded",
    "fingerprint-mismatch",
    "missing-version",
    "unsupported-schema-version",
    "event-id-conflict",
)


def ingest_records(
    db: Session,
    caller: Identity,
    records: list[RunRecord],
    supported_schema_versions: frozenset[int],
) -> IngestResponse:
    accepted: list[str] = []
    rejected: list[RejectedRecord] = []

    def reject(event_id: str, reason: str) -> None:
        assert reason in _TERMINAL_REASONS, f"unknown reject reason: {reason}"
        rejected.append(RejectedRecord(event_id=event_id, reason=reason, terminal=True))

    # which of these event_ids already exist, and under whose fingerprint? (idempotency +
    # cross-owner conflict detection)
    owner_by_id = _existing_owners(db, [r.event_id for r in records])

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
        if rec.schema_version not in supported_schema_versions:
            # storing a payload in a shape we don't claim to understand violates
            # CLAUDE.md invariant 5; terminal because retrying can't fix it (a newer
            # client re-emits under the new schema after its own migration).
            reject(rec.event_id, "unsupported-schema-version")
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

        # New row. Wrap the insert in a SAVEPOINT so that a race — another writer commits
        # this same new event_id between our pre-check and flush (two devices double-tapping
        # sync) — rolls back just this row instead of raising an unhandled IntegrityError
        # that 500s and un-acks the whole batch (FABLE C1). The loser of the race treats it
        # as an idempotent duplicate and reports it accepted. Portable: no dialect-specific
        # upsert; SQLite masks this locally but Postgres would not.
        try:
            with db.begin_nested():
                db.add(_to_row(rec))
                db.flush()
        except IntegrityError:
            # Lost an insert race: the row was committed by another writer between our
            # pre-check and this flush. Re-resolve the true owner before acking — a
            # same-owner race is an idempotent duplicate (accept), but a *different* owner
            # is a genuine conflict that must NOT be reported accepted, or we reintroduce
            # B1's silent data loss. Query the DB directly (not _existing_owners, which the
            # race test stubs) so we see committed reality.
            owner = db.execute(
                select(Run.fingerprint).where(Run.event_id == rec.event_id)
            ).scalar_one_or_none()
            if owner == caller.fingerprint:
                accepted.append(rec.event_id)
            else:
                reject(rec.event_id, "event-id-conflict")
            seen_in_batch.add(rec.event_id)
            continue
        seen_in_batch.add(rec.event_id)
        accepted.append(rec.event_id)

    db.commit()
    # dedupe while preserving first-seen order: an eventId repeated within the batch was
    # appended once per occurrence, but the client only needs it acked once (FABLE C6).
    accepted = list(dict.fromkeys(accepted))
    return IngestResponse(accepted=accepted, rejected=rejected)


def _existing_owners(db: Session, incoming_ids: list[str]) -> dict[str, str]:
    """Map each already-stored ``event_id`` in ``incoming_ids`` to its owner fingerprint."""
    return dict(
        db.execute(
            select(Run.event_id, Run.fingerprint).where(Run.event_id.in_(incoming_ids))
        ).all()
    )


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
