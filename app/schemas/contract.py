"""The wire contract — pydantic models mirroring SERVICE.md §5.

Conventions:
- camelCase aliases on the wire (matches the TS client); snake_case in Python.
- ``populate_by_name=True`` so tests/handlers can build models by either name.
- Version fields are opaque strings — the server stores and equality-compares them,
  never parses them.
- ``instruments`` is an OPEN object: extra keys are allowed and stored verbatim.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import re

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


def _camel(s: str) -> str:
    head, *rest = s.split("_")
    return head + "".join(w.capitalize() for w in rest)


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)


# --- bounded string types ----------------------------------------------------
# Every wire string is length-capped to match its DB column. SQLite ignores
# String(n) lengths, but Postgres raises DataError on overflow — so without these
# caps the "switch DB = one env var" invariant (CLAUDE.md #3) breaks on real input,
# and unbounded strings are an abuse vector. Caps mirror app/models/*: fingerprint/
# event_id/version/id 64, seed/spec_ref/manifest/recovery 128, consent 32, date 16.
_Str16 = Annotated[str, StringConstraints(max_length=16)]
_Str32 = Annotated[str, StringConstraints(max_length=32)]
_Str64 = Annotated[str, StringConstraints(max_length=64)]
_Str128 = Annotated[str, StringConstraints(max_length=128)]

# The player-chosen handle: trimmed, 1-32 chars, alphanumeric plus space/_/- and a
# leading alphanumeric. Keeps public leaderboard names free of control chars and
# homoglyph impersonation. [SEAM: set-core] the client registration UI must enforce
# the same rule (today it caps length only) so a valid handle never 422s.
Handle = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9 _\-]{0,31}$",
    ),
]


# --- shared sub-objects ------------------------------------------------------


class ClientVersions(_Wire):
    ruleset_version: _Str64
    content_version: _Str64


class Integrity(_Wire):
    """Mod gate. ``manifest_hash`` is the reserved slot for the future content-hash gate."""

    modded: bool = False
    manifest_hash: _Str128 | None = None


_DAILY_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RunContext(_Wire):
    kind: Literal["delve", "daily"]
    daily_date: _Str16 | None = None
    class_id: _Str64
    foe_id: _Str64 | None = None
    seed: _Str128
    spec_ref: _Str128

    @model_validator(mode="after")
    def _kind_matches_daily_date(self) -> RunContext:
        # kind and daily_date must agree, or the bests slice key collapses: a daily run with
        # daily_date=None keys into the (None) delve slice and can overwrite a delve best
        # (FABLE B4). daily <=> a well-formed date; delve => no date.
        if self.kind == "daily":
            if not (self.daily_date and _DAILY_DATE_RE.match(self.daily_date)):
                raise ValueError("kind 'daily' requires dailyDate as YYYY-MM-DD")
        elif self.daily_date is not None:
            raise ValueError("kind 'delve' must not carry a dailyDate")
        return self


class RunOutcome(_Wire):
    # Outcome numbers feed the bests read model (the phase-2 leaderboard seed) and rows
    # are append-only, so a garbage value accepted now is permanent leaderboard corruption
    # (e.g. terms=-999 becomes the fewest-terms best). Bound them: non-negative, with
    # generous sanity ceilings. A client emitting out-of-range values is broken, so a
    # pydantic 422 that fails the whole batch is the correct, loud response.
    result: Literal["win", "loss", "flee"]
    # terms == "sets matched to clear" (minimize); see SERVICE-RESPONSE.md §3.
    terms: int | None = Field(default=None, ge=0, le=100_000)
    real_time_ms: int | None = Field(default=None, ge=0, le=7 * 24 * 3600 * 1000)
    depth_reached: int | None = Field(default=None, ge=0, le=10_000)


# --- /register ---------------------------------------------------------------


class RegisterRequest(_Wire):
    fingerprint: _Str64
    handle: Handle
    consent_version: _Str32
    client: ClientVersions


class RegisterResponse(_Wire):
    token: str
    recovery_code: str
    handle: str


# --- /recover ----------------------------------------------------------------


class RecoverRequest(_Wire):
    recovery_code: _Str128
    fingerprint: _Str64  # the NEW fingerprint to bind


class RecoverResponse(_Wire):
    token: str
    handle: str


# --- /handle/available -------------------------------------------------------


class HandleAvailableResponse(_Wire):
    name: str
    available: bool


# --- the run record (unit of /ingest) ---------------------------------------


class RunRecord(_Wire):
    event_id: _Str64
    fingerprint: _Str64
    schema_version: int
    ruleset_version: _Str64
    content_version: _Str64
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
    emits — ``modded``, ``missing-version``, ``unsupported-schema-version``,
    ``fingerprint-mismatch``, ``event-id-conflict`` — is terminal. Any future retryable
    reject will carry ``terminal: false`` so the client branches on the boolean, never on
    parsing the reason string."""

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
