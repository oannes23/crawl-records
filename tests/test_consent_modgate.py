"""Criterion 6 — no run without a registered/consented identity; modded:true rejected."""

from __future__ import annotations

from tests.conftest import register, run_record


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_ingest_requires_identity(client):
    # no Authorization header → 401/403, never accepted
    r = client.post("/ingest", json={"records": [run_record("e1")]})
    assert r.status_code in (401, 403)

    # a bogus token is rejected
    r = client.post("/ingest", json={"records": [run_record("e1")]}, headers=_auth("garbage"))
    assert r.status_code == 401


def test_modded_record_rejected(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", integrity={"modded": True, "manifestHash": None})]},
        headers=_auth(tok),
    )
    assert r.status_code == 200
    body = r.json()
    assert "e1" not in body["accepted"]
    assert any(x["eventId"] == "e1" and x["reason"] == "modded" for x in body["rejected"])


def test_fingerprint_mismatch_rejected(client):
    tok = register(client, fingerprint="fp-1")["token"]
    # a record claiming a different fingerprint than the authenticated caller
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", fingerprint="someone-else")]},
        headers=_auth(tok),
    )
    body = r.json()
    assert "e1" not in body["accepted"]
    assert any(x["reason"] == "fingerprint-mismatch" for x in body["rejected"])
