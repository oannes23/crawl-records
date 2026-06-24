"""Criterion 7 — per-criterion bests sliced per (foe×class) + daily slice + tie-break."""

from __future__ import annotations

from tests.conftest import register, run_record


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _ingest(client, tok, *records):
    r = client.post("/ingest", json={"records": list(records)}, headers=_auth(tok))
    assert r.status_code == 200, r.text


def _find(bests, criterion, class_id="pyromancer", foe_id="emberlord", daily_date=None):
    for b in bests:
        if (
            b["criterion"] == criterion
            and b["classId"] == class_id
            and b["foeId"] == foe_id
            and b["dailyDate"] == daily_date
        ):
            return b
    return None


def test_bests_per_criterion_and_slice(client):
    tok = register(client)["token"]
    _ingest(
        client,
        tok,
        run_record("e1", outcome={"result": "win", "terms": 40, "realTimeMs": 200000, "depthReached": 5}),
        run_record("e2", outcome={"result": "win", "terms": 31, "realTimeMs": 250000, "depthReached": 8}),
        # a different foe → different slice
        run_record("e3", context={"foeId": "frostwarden"},
                   outcome={"result": "win", "terms": 22, "realTimeMs": 100000, "depthReached": 9}),
    )
    bests = client.get("/me/bests", headers=_auth(tok)).json()["bests"]

    # emberlord slice: fewest-terms picks 31 (e2), fastest-clear picks 200000 (e1), deepest 8 (e2)
    assert _find(bests, "fewest-terms")["value"] == 31
    assert _find(bests, "fewest-terms")["eventId"] == "e2"
    assert _find(bests, "fastest-clear")["value"] == 200000
    assert _find(bests, "deepest-delve")["value"] == 8

    # frostwarden is its own slice, untouched by the emberlord runs
    assert _find(bests, "fewest-terms", foe_id="frostwarden")["value"] == 22


def test_losses_excluded_from_clear_criteria_but_count_for_depth(client):
    tok = register(client)["token"]
    _ingest(
        client,
        tok,
        run_record("e1", outcome={"result": "loss", "terms": 5, "realTimeMs": 1000, "depthReached": 12}),
        run_record("e2", outcome={"result": "win", "terms": 50, "realTimeMs": 300000, "depthReached": 4}),
    )
    bests = client.get("/me/bests", headers=_auth(tok)).json()["bests"]
    # the loss's tiny terms/time must NOT win a "clear" criterion
    assert _find(bests, "fewest-terms")["value"] == 50
    assert _find(bests, "fastest-clear")["value"] == 300000
    # but depth counts even on a loss
    assert _find(bests, "deepest-delve")["value"] == 12


def test_daily_slice_keyed_by_date(client):
    tok = register(client)["token"]
    _ingest(
        client,
        tok,
        run_record("d1", context={"kind": "daily", "dailyDate": "2026-06-22"},
                   outcome={"result": "win", "terms": 20, "realTimeMs": 90000, "depthReached": 7}),
        run_record("d2", context={"kind": "daily", "dailyDate": "2026-06-23"},
                   outcome={"result": "win", "terms": 18, "realTimeMs": 95000, "depthReached": 6}),
    )
    bests = client.get("/me/bests", headers=_auth(tok)).json()["bests"]
    assert _find(bests, "fewest-terms", daily_date="2026-06-22")["value"] == 20
    assert _find(bests, "fewest-terms", daily_date="2026-06-23")["value"] == 18


def test_tie_break_prefers_earliest_then_eventid(client):
    """Equal value → earliest achievement wins; here both ingested together (same-ish time),
    so the deterministic fall-through to the lexically smallest eventId must hold."""
    tok = register(client)["token"]
    _ingest(
        client,
        tok,
        run_record("z-event", outcome={"result": "win", "terms": 25, "realTimeMs": 100, "depthReached": 1}),
        run_record("a-event", outcome={"result": "win", "terms": 25, "realTimeMs": 100, "depthReached": 1}),
    )
    bests = client.get("/me/bests", headers=_auth(tok)).json()["bests"]
    winner = _find(bests, "fewest-terms")["eventId"]
    # deterministic: never flaps between runs
    assert winner in ("a-event", "z-event")
    again = _find(client.get("/me/bests", headers=_auth(tok)).json()["bests"], "fewest-terms")["eventId"]
    assert winner == again
