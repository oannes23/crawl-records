"""Criterion 8 — /daily is a pure function of date (+ active versions)."""

from __future__ import annotations

from tests.conftest import register, run_record  # noqa: F401  (kept for symmetry)


def test_same_date_same_descriptor(client):
    a = client.get("/daily?date=2026-06-22").json()
    b = client.get("/daily?date=2026-06-22").json()
    assert a == b


def test_different_dates_differ(client):
    a = client.get("/daily?date=2026-06-22").json()
    b = client.get("/daily?date=2026-06-23").json()
    assert a["seed"] != b["seed"]
    assert a["date"] != b["date"]


def test_default_date_is_today_utc(client):
    r = client.get("/daily")
    assert r.status_code == 200
    assert len(r.json()["date"]) == 10  # YYYY-MM-DD


def test_malformed_date_rejected(client):
    r = client.get("/daily?date=not-a-date")
    assert r.status_code == 400


def test_date_is_normalized(client):
    """FABLE B3: a non-zero-padded date normalizes to the padded form and yields the
    identical descriptor, so two clients asking for the same calendar day agree."""
    unpadded = client.get("/daily?date=2026-7-1").json()
    padded = client.get("/daily?date=2026-07-01").json()
    assert unpadded["date"] == "2026-07-01"
    assert unpadded == padded


def test_criteria_are_the_mvp_set(client):
    crit = client.get("/daily?date=2026-06-22").json()["criteria"]
    assert crit == ["fewest-terms", "fastest-clear", "deepest-delve"]
