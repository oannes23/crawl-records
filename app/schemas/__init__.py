"""Pydantic wire models — THE published contract (source of truth for client codegen)."""

from app.schemas.contract import (
    BestEntry,
    BestsResponse,
    ClientVersions,
    DailyDescriptor,
    HandleAvailableResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    Integrity,
    RecoverRequest,
    RecoverResponse,
    RegisterRequest,
    RegisterResponse,
    RunContext,
    RunOutcome,
    RunRecord,
)

__all__ = [
    "BestEntry",
    "BestsResponse",
    "ClientVersions",
    "DailyDescriptor",
    "HandleAvailableResponse",
    "HealthResponse",
    "IngestRequest",
    "IngestResponse",
    "Integrity",
    "RecoverRequest",
    "RecoverResponse",
    "RegisterRequest",
    "RegisterResponse",
    "RunContext",
    "RunOutcome",
    "RunRecord",
]
