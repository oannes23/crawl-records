"""The §4 MVP API surface. JSON over HTTP(S); these routes ARE the published contract."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_identity
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Identity
from app.schemas import (
    BestsResponse,
    DailyDescriptor,
    HandleAvailableResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    RecoverRequest,
    RecoverResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.services import bests as bests_svc
from app.services import daily as daily_svc
from app.services import identity as identity_svc
from app.services import ingest as ingest_svc

router = APIRouter(tags=["embassy"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        schema_version=settings.schema_version,
        ruleset_version=settings.ruleset_version,
        content_version=settings.content_version,
        consent_version=settings.consent_version,
    )


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Liveness probe for container HEALTHCHECK / uptime monitoring.

    Deliberately NOT part of the wire contract (``include_in_schema=False`` keeps it out
    of ``openapi.json``) and deliberately does no DB work: it answers only "the process is
    up and serving", nothing more. ``/health`` above is the separate, contract-bound
    version handshake the client reads — don't conflate the two.
    """
    return {"status": "ok"}


@router.get("/handle/available", response_model=HandleAvailableResponse)
def handle_available(
    name: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
) -> HandleAvailableResponse:
    return identity_svc.handle_available(db, name)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    return identity_svc.register(db, req)


@router.post("/recover", response_model=RecoverResponse)
def recover(req: RecoverRequest, db: Session = Depends(get_db)) -> RecoverResponse:
    return identity_svc.recover(db, req)


@router.post("/ingest", response_model=IngestResponse)
def ingest(
    req: IngestRequest,
    caller: Identity = Depends(require_identity),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    if not settings.enable_ingest:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ingest disabled")
    if len(req.records) > settings.max_batch:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"batch exceeds max_batch={settings.max_batch}",
        )
    return ingest_svc.ingest_records(
        db, caller, req.records, frozenset({settings.schema_version})
    )


@router.get("/me/bests", response_model=BestsResponse)
def me_bests(
    caller: Identity = Depends(require_identity),
    db: Session = Depends(get_db),
) -> BestsResponse:
    return bests_svc.compute_bests(db, caller.fingerprint)


@router.get("/daily", response_model=DailyDescriptor)
def daily(
    date: str = Query("", description="YYYY-MM-DD; defaults to today (UTC)"),
    settings: Settings = Depends(get_settings),
) -> DailyDescriptor:
    try:
        resolved = daily_svc.validate_date(date)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date must be YYYY-MM-DD") from None
    return daily_svc.daily_descriptor(resolved, settings)
