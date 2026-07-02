"""Admin panel — read-only browse over the corpus, gated by HTTP Basic.

Mounted under ``/admin``; every route depends on ``require_admin`` and is tagged
``admin`` so ``scripts/export_openapi.py`` can strip it from the published client
contract. HTML pages render with Jinja2; the ``/admin/api/*`` routes return JSON for
the in-page vanilla-JS filtering.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_db
from app.schemas.contract import RunSummary
from app.services import admin as admin_svc
from app.services import bests as bests_svc
from app.services import daily as daily_svc

router = APIRouter(prefix="/admin", tags=["admin"])

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


# --- HTML pages --------------------------------------------------------------


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def admin_home(request: Request, _: str = Depends(require_admin)) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(request, "admin_home.html", {"page": "home"})


@router.get("/runs", response_class=HTMLResponse, include_in_schema=False)
def admin_runs(request: Request, _: str = Depends(require_admin)) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(request, "admin_runs.html", {"page": "runs"})


@router.get("/runs/{event_id}", response_class=HTMLResponse, include_in_schema=False)
def admin_run_detail(
    request: Request,
    event_id: str,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    run = admin_svc.get_run(db, event_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return _TEMPLATES.TemplateResponse(
        request, "admin_run_detail.html", {"page": "runs", "run": run}
    )


@router.get("/identities", response_class=HTMLResponse, include_in_schema=False)
def admin_identities(
    request: Request, _: str = Depends(require_admin), db: Session = Depends(get_db)
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request,
        "admin_identities.html",
        {"page": "identities", "identities": admin_svc.list_identities(db)},
    )


@router.get("/bests", response_class=HTMLResponse, include_in_schema=False)
def admin_bests(
    request: Request,
    fingerprint: str = Query(""),
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    bests = bests_svc.compute_bests(db, fingerprint).bests if fingerprint else []
    return _TEMPLATES.TemplateResponse(
        request,
        "admin_bests.html",
        {"page": "bests", "fingerprint": fingerprint, "bests": bests},
    )


@router.get("/daily", response_class=HTMLResponse, include_in_schema=False)
def admin_daily(
    request: Request,
    date: str = Query(""),
    _: str = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        resolved = daily_svc.validate_date(date)
        descriptor = daily_svc.daily_descriptor(resolved, settings)
    except ValueError:
        descriptor = None
    return _TEMPLATES.TemplateResponse(
        request, "admin_daily.html", {"page": "daily", "date": date, "descriptor": descriptor}
    )


@router.get("/instruments", response_class=HTMLResponse, include_in_schema=False)
def admin_instruments(
    request: Request, _: str = Depends(require_admin), db: Session = Depends(get_db)
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request,
        "admin_instruments.html",
        {"page": "instruments", "agg": admin_svc.instrument_aggregates(db)},
    )


@router.get("/health", response_class=HTMLResponse, include_in_schema=False)
def admin_health(
    request: Request, _: str = Depends(require_admin), settings: Settings = Depends(get_settings)
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request, "admin_health.html", {"page": "health", "settings": settings}
    )


# --- JSON layer (for in-page filtering) -------------------------------------


@router.get("/api/runs", include_in_schema=False)
def api_runs(
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
    fingerprint: str = Query(""),
    handle: str = Query(""),
    class_id: str = Query(""),
    foe_id: str = Query(""),
    kind: str = Query(""),
    result: str = Query(""),
    ruleset_version: str = Query(""),
    sort: str = Query("created_at"),
    desc: bool = Query(True),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    rows, total = admin_svc.list_runs(
        db,
        fingerprint=fingerprint or None,
        handle=handle or None,
        class_id=class_id or None,
        foe_id=foe_id or None,
        kind=kind or None,
        result=result or None,
        ruleset_version=ruleset_version or None,
        sort=sort,
        desc=desc,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "runs": [
                RunSummary(
                    event_id=r.event_id,
                    fingerprint=r.fingerprint,
                    kind=r.kind,
                    class_id=r.class_id,
                    foe_id=r.foe_id,
                    result=r.result,
                    terms=r.terms,
                    real_time_ms=r.real_time_ms,
                    depth_reached=r.depth_reached,
                    daily_date=r.daily_date,
                    ruleset_version=r.ruleset_version,
                    content_version=r.content_version,
                    created_at=r.created_at.isoformat() if r.created_at else None,
                ).model_dump(by_alias=True)
                for r in rows
            ],
        }
    )
