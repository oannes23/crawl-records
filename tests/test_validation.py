"""Wire-input validation gates (FABLE B5/B2/B4).

These prove the contract rejects malformed/abusive input at the pydantic layer (422)
rather than storing it — the pre-Postgres safety net (B5), the leaderboard-integrity
bounds (B2), and the bests-slice coherence rule (B4).
"""

from __future__ import annotations

from .conftest import register, run_record


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


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
