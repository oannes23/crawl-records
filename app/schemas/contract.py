"""The wire contract — pydantic models mirroring SERVICE.md §5.

Conventions:
- camelCase aliases on the wire (matches the TS client); snake_case in Python.
- ``populate_by_name=True`` so tests/handlers can build models by either name.
- Version fields are opaque strings — the server stores and equality-compares them,
  never parses them.
- ``instruments`` is an OPEN object: extra keys are allowed and stored verbatim.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _camel(s: str) -> str:
    head, *rest = s.split("_")
    return head + "".join(w.capitalize() for w in rest)


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)


# --- shared sub-objects ------------------------------------------------------


class ClientVersions(_Wire):
    ruleset_version: str
    content_version: str


class Integrity(_Wire):
    """Mod gate. ``manifest_hash`` is the reserved slot for the future content-hash gate."""

    modded: bool = False
    manifest_hash: str | None = None


class RunContext(_Wire):
    kind: Literal["delve", "daily"]
    daily_date: str | None = None
    class_id: str
    foe_id: str | None = None
    seed: str
    spec_ref: str


class RunOutcome(_Wire):
    result: Literal["win", "loss", "flee"]
    # terms == "sets matched to clear" (minimize); see SERVICE-RESPONSE.md §3.
    terms: int | None = None
    real_time_ms: int | None = None
    depth_reached: int | None = None


# --- /register ---------------------------------------------------------------


class RegisterRequest(_Wire):
    fingerprint: str
    handle: str
    consent_version: str
    client: ClientVersions


class RegisterResponse(_Wire):
    token: str
    recovery_code: str
    handle: str


# --- /recover ----------------------------------------------------------------


class RecoverRequest(_Wire):
    recovery_code: str
    fingerprint: str  # the NEW fingerprint to bind


class RecoverResponse(_Wire):
    token: str
    handle: str


# --- /handle/available -------------------------------------------------------


class HandleAvailableResponse(_Wire):
    name: str
    available: bool


# --- the run record (unit of /ingest) ---------------------------------------


class RunRecord(_Wire):
    event_id: str
    fingerprint: str
    schema_version: int
    ruleset_version: str
    content_version: str
    integrity: Integrity = Field(default_factory=Integrity)
    context: RunContext
    outcome: RunOutcome
    actions: list[Any] = Field(default_factory=list)
    instruments: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(_Wire):
    records: list[RunRecord]


class RejectedRecord(_Wire):
    """A per-record ingest rejection. ``terminal`` tells the client whether to quarantine/
    drop the record (true) or keep it in the outbox and retry (false). Every reason the MVP
    emits — ``modded``, ``missing-version``, ``fingerprint-mismatch`` — is terminal. Any
    future retryable reject will carry ``terminal: false`` so the client branches on the
    boolean, never on parsing the reason string."""

    event_id: str
    reason: str
    terminal: bool = True


class IngestResponse(_Wire):
    accepted: list[str]  # the event_ids stored/confirmed (idempotent)
    rejected: list[RejectedRecord] = Field(default_factory=list)


# --- /me/bests ---------------------------------------------------------------


class BestEntry(_Wire):
    criterion: str
    class_id: str
    foe_id: str | None = None
    daily_date: str | None = None
    value: int
    event_id: str
    achieved_at: str


class BestsResponse(_Wire):
    bests: list[BestEntry]


# --- /daily ------------------------------------------------------------------


class DailySpec(_Wire):
    """An OPTIONAL authored-daily channel (SERVICE-REPLY.md item 1, path b).

    When present, the client uses these selections instead of deriving them from ``seed``;
    every id is validated against the client's LOCAL registry (an unknown id ⇒ the daily is
    unavailable, handled exactly like a version mismatch — never a content download). When
    ``spec`` is absent the client derives all selections from ``seed`` alone (path a, the MVP
    default). The field exists now so authored dailies are not a future schema break.
    ``params`` is an open object for per-daily knobs (modifiers, mutators) the client reads.
    """

    class_id: str | None = None
    foe_id: str | None = None
    dungeon_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class DailyDescriptor(_Wire):
    date: str
    seed: str
    spec_ref: str
    ruleset_version: str
    content_version: str
    criteria: list[str]
    spec: DailySpec | None = None  # absent ⇒ derive selections from seed (path a)


# --- /health -----------------------------------------------------------------


class HealthResponse(_Wire):
    status: Literal["ok"] = "ok"
    schema_version: int
    ruleset_version: str
    content_version: str
    consent_version: str
