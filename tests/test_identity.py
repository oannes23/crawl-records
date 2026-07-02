"""Criterion 5 — handle uniqueness, /recover rebind, recovery codes stored hashed."""

from __future__ import annotations

from sqlalchemy import select

from app.models import Identity, Run
from tests.conftest import _auth, register, run_record


def test_handle_uniqueness_first_come(client):
    register(client, handle="Ashling", fingerprint="fp-1")

    # availability now reports taken (case-insensitive)
    assert client.get("/handle/available?name=ashling").json()["available"] is False

    # a second claim of the same handle (different fingerprint) is rejected
    r = client.post(
        "/register",
        json={
            "fingerprint": "fp-2",
            "handle": "ASHLING",
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    assert r.status_code == 409


def test_recovery_codes_stored_hashed(client, engine):
    reg = register(client)
    code = reg["recoveryCode"]
    with engine.connect() as conn:
        stored = conn.execute(select(Identity.recovery_code_hash)).scalar_one()
    assert stored != code  # never stored in the clear
    assert len(stored) == 64  # sha256 hex


def test_recover_rebinds_new_fingerprint_and_keeps_history(client, engine):
    reg = register(client, fingerprint="old-fp")
    tok = reg["token"]
    code = reg["recoveryCode"]
    client.post("/ingest", json={"records": [run_record("e1", fingerprint="old-fp")]}, headers=_auth(tok))

    # new install: rebind to a fresh fingerprint via the recovery code
    r = client.post("/recover", json={"recoveryCode": code, "fingerprint": "new-fp"})
    assert r.status_code == 200
    new_tok = r.json()["token"]
    assert new_tok != tok  # fresh token issued

    # the identity moved to the new fingerprint AND the old run followed it
    with engine.connect() as conn:
        ids = conn.execute(select(Identity.fingerprint)).scalars().all()
        run_fp = conn.execute(select(Run.fingerprint)).scalar_one()
    assert ids == ["new-fp"]
    assert run_fp == "new-fp"

    # the new token authenticates; bests reflect the carried-over run
    bests = client.get("/me/bests", headers=_auth(new_tok)).json()["bests"]
    assert any(b["eventId"] == "e1" for b in bests)


def test_bad_recovery_code_rejected(client):
    register(client)
    r = client.post("/recover", json={"recoveryCode": "not-a-real-code", "fingerprint": "x"})
    assert r.status_code == 404
