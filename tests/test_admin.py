"""Admin panel smoke tests — auth gate + each view renders / returns data.

Also asserts the contract-isolation invariant: no /admin path leaks into the published
OpenAPI schema (criterion 12 / client-codegen hygiene).
"""

from __future__ import annotations

from app.main import app
from tests.conftest import _auth, register, run_record

ADMIN = ("admin", "changeme")  # the test-default config creds


def test_admin_requires_auth(client):
    for path in ["/admin/", "/admin/runs", "/admin/identities", "/admin/instruments", "/admin/health"]:
        assert client.get(path).status_code == 401


def test_admin_pages_render(client):
    for path in ["/admin/", "/admin/runs", "/admin/identities", "/admin/bests",
                 "/admin/daily", "/admin/instruments", "/admin/health"]:
        r = client.get(path, auth=ADMIN)
        assert r.status_code == 200, path
        assert "EMBASSY ADMIN" in r.text


def test_admin_runs_json_and_detail(client):
    tok = register(client)["token"]
    client.post("/ingest", json={"records": [run_record("e1")]}, headers=_auth(tok))

    data = client.get("/admin/api/runs", auth=ADMIN).json()
    assert data["total"] == 1
    assert data["runs"][0]["eventId"] == "e1"

    detail = client.get("/admin/runs/e1", auth=ADMIN)
    assert detail.status_code == 200
    assert "e1" in detail.text


def test_admin_runs_json_handle_no_match(client):
    """A3: a handle filter that resolves to no fingerprint matches zero runs (via
    sqlalchemy false()), not everything and not an error."""
    tok = register(client)["token"]
    client.post("/ingest", json={"records": [run_record("e1")]}, headers=_auth(tok))

    data = client.get("/admin/api/runs", auth=ADMIN, params={"handle": "NobodyHere"}).json()
    assert data["total"] == 0
    assert data["runs"] == []


def test_admin_instruments_aggregate(client):
    tok = register(client)["token"]
    client.post(
        "/ingest",
        json={"records": [run_record("e1", instruments={"trapSpringRate": 0.3, "setsPerRound": 4.0})]},
        headers=_auth(tok),
    )
    r = client.get("/admin/instruments", auth=ADMIN)
    assert r.status_code == 200


def test_admin_excluded_from_published_contract(client):
    schema = app.openapi()
    leaked = [p for p in schema["paths"] if p.startswith("/admin")]
    assert leaked == []
