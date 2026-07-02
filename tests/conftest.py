"""Test fixtures — a fresh temp-SQLite app per test via dependency overrides.

We don't touch the module-level engine; instead we build a per-test engine on a temp
file, create the schema from ``Base.metadata``, and override ``get_db`` (and, where a test
needs custom versions, ``get_settings``). This keeps tests isolated and fast while still
exercising the real SQLite path (criterion 1).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base, get_db
from app.main import app


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def engine(db_url: str):
    eng = create_engine(db_url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    def _get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def settings_override():
    """Returns a setter that overrides get_settings with a custom Settings for a test."""
    from app.config import get_settings

    def _set(**kwargs):
        base = Settings()
        merged = base.model_copy(update=kwargs)
        app.dependency_overrides[get_settings] = lambda: merged
        return merged

    yield _set
    app.dependency_overrides.pop(get_settings, None)


# --- helpers ----------------------------------------------------------------


def _auth(token):
    """Bearer auth header for a player token (shared across the ingest/bests tests)."""
    return {"Authorization": f"Bearer {token}"}


def register(client: TestClient, handle="Ashling", fingerprint="fp-1"):
    r = client.post(
        "/register",
        json={
            "fingerprint": fingerprint,
            "handle": handle,
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def run_record(event_id, fingerprint="fp-1", **over):
    rec = {
        "eventId": event_id,
        "fingerprint": fingerprint,
        "schemaVersion": 1,
        "rulesetVersion": "1.0.0",
        "contentVersion": "1.0.0",
        "integrity": {"modded": False, "manifestHash": None},
        "context": {
            "kind": "delve",
            "dailyDate": None,
            "classId": "pyromancer",
            "foeId": "emberlord",
            "seed": "seed-1",
            "specRef": "spec-1",
        },
        "outcome": {"result": "win", "terms": 37, "realTimeMs": 184210, "depthReached": 6},
        "actions": [],
        "instruments": {},
    }
    # shallow-merge overrides into nested dicts
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(rec.get(k), dict):
            rec[k] = {**rec[k], **v}
        else:
            rec[k] = v
    return rec
