"""Wire-input validation gates (FABLE B5/B2/B4).

These prove the contract rejects malformed/abusive input at the pydantic layer (422)
rather than storing it — the pre-Postgres safety net (B5), the leaderboard-integrity
bounds (B2), and the bests-slice coherence rule (B4).
"""

from __future__ import annotations

from .conftest import _auth, register, run_record


# --- B5: string bounds + handle charset -------------------------------------


def test_overlong_fingerprint_rejected(client):
    r = client.post(
        "/register",
        json={
            "fingerprint": "f" * 65,
            "handle": "Ashling",
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    assert r.status_code == 422, r.text


def test_abusive_handle_rejected(client):
    # the §2 repro: a 500-char handle used to register at full length
    r = client.post(
        "/register",
        json={
            "fingerprint": "fp-x",
            "handle": "A" * 500,
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    assert r.status_code == 422, r.text


def test_handle_charset_rejected(client):
    # control chars / punctuation outside the leaderboard-safe set
    r = client.post(
        "/register",
        json={
            "fingerprint": "fp-y",
            "handle": "Ash<script>",
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    assert r.status_code == 422, r.text


def test_handle_is_trimmed(client):
    r = client.post(
        "/register",
        json={
            "fingerprint": "fp-z",
            "handle": "  Ashling  ",
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["handle"] == "Ashling"


def test_normal_handle_passes(client):
    r = client.post(
        "/register",
        json={
            "fingerprint": "fp-ok",
            "handle": "Ash_the-Delver 2",
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    assert r.status_code == 201, r.text


def test_overlong_event_id_rejected(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e" * 65)]},
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text


# --- batch semantics: a pydantic violation fails the WHOLE batch ------------


def test_one_invalid_record_fails_the_whole_batch(client):
    """Pins the documented tradeoff (FABLE B2 / QA finding #2): a schema-level violation
    (bounds/charset/kind) is a raw 422 that rejects the ENTIRE /ingest batch — unlike a
    business-gate reject (modded, event-id-conflict) which partial-accepts. A conforming
    client never sends malformed records; if this behavior ever changes to per-record
    rejection, update SERVICE-RESPONSE.md and this test together."""
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={
            "records": [
                run_record("good-0"),
                run_record("good-1"),
                run_record("bad", outcome={"result": "win", "terms": -1}),
            ]
        },
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text
    # nothing from the batch was stored — not even the two valid records
    assert client.get("/me/bests", headers=_auth(tok)).json()["bests"] == []


# --- B2: outcome bounds -----------------------------------------------------


def test_negative_terms_rejected(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", outcome={"result": "win", "terms": -999})]},
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text
    assert client.get("/me/bests", headers=_auth(tok)).json()["bests"] == []


def test_absurd_outcome_rejected(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", outcome={"result": "win", "depthReached": 10_001})]},
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text


def test_outcome_boundary_values_pass(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={
            "records": [
                run_record("e1", outcome={"result": "win", "terms": 0, "realTimeMs": 0, "depthReached": 0})
            ]
        },
        headers=_auth(tok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == ["e1"]


# --- B4: kind/dailyDate cross-validation ------------------------------------


def test_daily_without_date_rejected(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", context={"kind": "daily", "dailyDate": None})]},
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text
    assert client.get("/me/bests", headers=_auth(tok)).json()["bests"] == []


def test_delve_with_date_rejected(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", context={"kind": "delve", "dailyDate": "2026-07-01"})]},
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text


def test_daily_with_impossible_date_rejected(client):
    # regex-shaped but not a real calendar date (QA finding #4)
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", context={"kind": "daily", "dailyDate": "9999-99-99"})]},
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text


def test_daily_with_unpadded_date_rejected(client):
    # /daily normalizes to zero-padded; the bests slice key must stay canonical
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", context={"kind": "daily", "dailyDate": "2026-7-1"})]},
        headers=_auth(tok),
    )
    assert r.status_code == 422, r.text


def test_valid_daily_and_delve_pass(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={
            "records": [
                run_record("d1", context={"kind": "delve", "dailyDate": None}),
                run_record("d2", context={"kind": "daily", "dailyDate": "2026-07-01"}),
            ]
        },
        headers=_auth(tok),
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["accepted"]) == {"d1", "d2"}
