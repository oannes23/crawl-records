"""Proving tests for the SERVICE-REPLY.md follow-ups (items 1, 3, 4)."""

from __future__ import annotations

import json

from tests.conftest import register, run_record


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- item 1: structured authored-daily spec ---------------------------------


def test_daily_spec_absent_by_default(client):
    """Path a (MVP default): no daily_file → descriptor carries spec=None; client derives
    selections from the seed."""
    d = client.get("/daily?date=2026-06-22").json()
    assert "spec" in d
    assert d["spec"] is None


def test_daily_authored_spec_when_configured(client, settings_override, tmp_path):
    """Path b: an operator-authored daily file makes the server specify selections, without
    a schema break — and it stays deterministic for the date."""
    f = tmp_path / "dailies.json"
    f.write_text(
        json.dumps(
            {
                "2026-07-04": {
                    "classId": "pyromancer",
                    "foeId": "emberlord",
                    "dungeonId": "the-warren",
                    "params": {"mutator": "double-dread"},
                }
            }
        )
    )
    settings_override(daily_file=str(f))

    d = client.get("/daily?date=2026-07-04").json()
    assert d["spec"]["classId"] == "pyromancer"
    assert d["spec"]["foeId"] == "emberlord"
    assert d["spec"]["dungeonId"] == "the-warren"
    assert d["spec"]["params"] == {"mutator": "double-dread"}

    # a date with no authored entry still falls back to path a
    other = client.get("/daily?date=2026-07-05").json()
    assert other["spec"] is None

    # determinism holds for the authored date
    assert client.get("/daily?date=2026-07-04").json() == d


# --- item 3: recover when only the token is lost (fingerprint survives) ------


def test_recover_with_original_fingerprint_reissues_token(client):
    """A partial save-clear drops the token but keeps the original fingerprint. Presenting
    the ORIGINAL fingerprint to /recover must re-issue a token (no 409), so the player is
    never locked out."""
    reg = register(client, fingerprint="orig-fp")
    old_token = reg["token"]
    code = reg["recoveryCode"]

    r = client.post("/recover", json={"recoveryCode": code, "fingerprint": "orig-fp"})
    assert r.status_code == 200
    new_token = r.json()["token"]
    assert new_token != old_token  # fresh token issued

    # the new token authenticates; the old one is now dead
    assert client.get("/me/bests", headers=_auth(new_token)).status_code == 200
    assert client.get("/me/bests", headers=_auth(old_token)).status_code == 401


# --- item 4: reject reasons are terminal ------------------------------------


def test_rejects_are_marked_terminal(client):
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={
            "records": [
                run_record("e1", integrity={"modded": True, "manifestHash": None}),
                run_record("e2", fingerprint="someone-else"),
            ]
        },
        headers=_auth(tok),
    )
    rejected = r.json()["rejected"]
    reasons = {x["reason"]: x for x in rejected}
    assert reasons["modded"]["terminal"] is True
    assert reasons["fingerprint-mismatch"]["terminal"] is True
    assert {"eventId", "reason", "terminal"} <= set(rejected[0].keys())
