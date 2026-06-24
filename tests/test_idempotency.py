"""Criterion 3 — idempotent /ingest: duplicates + partial re-upload converge to one row."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import Run
from tests.conftest import register, run_record


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_duplicate_and_partial_batch_converge(client, engine):
    tok = register(client)["token"]

    # initial batch: two records
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1"), run_record("e2")]},
        headers=_auth(tok),
    )
    assert r.status_code == 200
    assert set(r.json()["accepted"]) == {"e1", "e2"}

    # re-upload e1 (dup) + e3 (new) — partial overlap
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1"), run_record("e3")]},
        headers=_auth(tok),
    )
    assert set(r.json()["accepted"]) == {"e1", "e3"}

    # exact same eventId twice within ONE batch
    r = client.post(
        "/ingest",
        json={"records": [run_record("e4"), run_record("e4")]},
        headers=_auth(tok),
    )
    assert r.json()["accepted"].count("e4") >= 1

    # ground truth: one stored row per distinct eventId, never doubled
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(Run)).scalar_one()
        per_id = dict(
            conn.execute(select(Run.event_id, func.count()).group_by(Run.event_id)).all()
        )
    assert total == 4  # e1..e4
    assert all(c == 1 for c in per_id.values())
