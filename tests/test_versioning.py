"""Criterion 4 — versioning persisted; /health advertises; /daily refuses cross-version."""

from __future__ import annotations

from sqlalchemy import select

from app.models import Run
from tests.conftest import register, run_record


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_advertises_versions(client, settings_override):
    settings_override(
        ruleset_version="9.9.9", content_version="8.8.8", consent_version="2", schema_version=1
    )
    r = client.get("/health")
    body = r.json()
    assert body["rulesetVersion"] == "9.9.9"
    assert body["contentVersion"] == "8.8.8"
    assert body["consentVersion"] == "2"
    assert body["schemaVersion"] == 1


def test_every_run_persists_versions(client, engine):
    tok = register(client)["token"]
    client.post("/ingest", json={"records": [run_record("e1")]}, headers=_auth(tok))
    with engine.connect() as conn:
        row = conn.execute(
            select(Run.schema_version, Run.ruleset_version, Run.content_version)
        ).one()
    assert row.schema_version == 1
    assert row.ruleset_version == "1.0.0"
    assert row.content_version == "1.0.0"


def test_unsupported_schema_version_rejected(client):
    """FABLE B6: a record whose schemaVersion the server doesn't support is rejected
    terminal, not silently stored in a shape the server doesn't understand."""
    tok = register(client)["token"]
    r = client.post(
        "/ingest",
        json={"records": [run_record("e1", schemaVersion=999)]},
        headers=_auth(tok),
    )
    body = r.json()
    assert body["accepted"] == []
    assert body["rejected"][0]["reason"] == "unsupported-schema-version"
    assert body["rejected"][0]["terminal"] is True

    # the supported version still passes
    r = client.post(
        "/ingest",
        json={"records": [run_record("e2", schemaVersion=1)]},
        headers=_auth(tok),
    )
    assert r.json()["accepted"] == ["e2"]


def test_daily_is_version_pinned(client, settings_override):
    """The daily descriptor carries + depends on the active versions: changing them changes
    the seed, so a client on a mismatched version cannot claim board-equality."""
    settings_override(ruleset_version="1.0.0", content_version="1.0.0")
    d1 = client.get("/daily?date=2026-06-22").json()

    settings_override(ruleset_version="2.0.0", content_version="1.0.0")
    d2 = client.get("/daily?date=2026-06-22").json()

    assert d1["date"] == d2["date"] == "2026-06-22"
    assert d1["rulesetVersion"] != d2["rulesetVersion"]
    assert d1["seed"] != d2["seed"]  # version is folded into the seed → no cross-version equality
