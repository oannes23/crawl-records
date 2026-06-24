"""Insert a small synthetic corpus so the admin UI has something to browse.

Registers a couple of identities and ingests a handful of runs across classes/foes/kinds.
Uses the public API in-process (honors every gate). Run via ``make seed`` against your
configured DB (SQLite by default). Idempotent on eventId, so re-running is safe.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

CLIENT = TestClient(app)


def _register(handle: str, fingerprint: str) -> str:
    r = CLIENT.post(
        "/register",
        json={
            "fingerprint": fingerprint,
            "handle": handle,
            "consentVersion": "1",
            "client": {"rulesetVersion": "1.0.0", "contentVersion": "1.0.0"},
        },
    )
    if r.status_code == 409:  # already seeded — recover a token is overkill; skip
        print(f"  {handle} already registered, skipping new token")
        return ""
    return r.json()["token"]


def _ingest(token: str, records: list[dict]) -> None:
    if not token:
        return
    r = CLIENT.post("/ingest", json={"records": records}, headers={"Authorization": f"Bearer {token}"})
    print("  ingest:", r.json())


def _rec(event_id, fp, cls, foe, kind, daily_date, result, terms, ms, depth, instruments):
    return {
        "eventId": event_id,
        "fingerprint": fp,
        "schemaVersion": 1,
        "rulesetVersion": "1.0.0",
        "contentVersion": "1.0.0",
        "integrity": {"modded": False, "manifestHash": None},
        "context": {
            "kind": kind,
            "dailyDate": daily_date,
            "classId": cls,
            "foeId": foe,
            "seed": f"seed-{event_id}",
            "specRef": f"spec-{event_id}",
        },
        "outcome": {"result": result, "terms": terms, "realTimeMs": ms, "depthReached": depth},
        "actions": [{"t": 0, "verb": "attack"}, {"t": 1, "verb": "defend"}],
        "instruments": instruments,
    }


def main() -> None:
    print("seeding Ashling…")
    t1 = _register("Ashling", "fp-ashling")
    _ingest(t1, [
        _rec("a1", "fp-ashling", "pyromancer", "emberlord", "delve", None, "win", 37, 184000, 6,
             {"trapSpringRate": 0.31, "setsPerRound": 4.2, "reshareSharePlayer": 0.67, "setsMatched": 38}),
        _rec("a2", "fp-ashling", "pyromancer", "emberlord", "delve", None, "win", 31, 150000, 8,
             {"trapSpringRate": 0.28, "setsPerRound": 4.9, "reshareSharePlayer": 0.69, "setsMatched": 33}),
        _rec("a3", "fp-ashling", "pyromancer", "frostwarden", "delve", None, "loss", None, None, 11,
             {"trapSpringRate": 0.33, "setsPerRound": 3.1, "reshareSharePlayer": 0.62, "setsMatched": 20}),
        _rec("a4", "fp-ashling", "pyromancer", "emberlord", "daily", "2026-06-23", "win", 24, 99000, 7,
             {"trapSpringRate": 0.30, "setsPerRound": 5.1, "reshareSharePlayer": 0.70, "setsMatched": 26}),
    ])

    print("seeding Bram…")
    t2 = _register("Bram", "fp-bram")
    _ingest(t2, [
        _rec("b1", "fp-bram", "sentinel", "emberlord", "delve", None, "win", 45, 210000, 5,
             {"trapSpringRate": 0.35, "setsPerRound": 3.4, "reshareSharePlayer": 0.64, "setsMatched": 47}),
        _rec("b2", "fp-bram", "sentinel", "emberlord", "daily", "2026-06-23", "win", 29, 120000, 6,
             {"trapSpringRate": 0.29, "setsPerRound": 4.0, "reshareSharePlayer": 0.66, "setsMatched": 31}),
    ])

    print("done.")


if __name__ == "__main__":
    main()
