"""FastAPI application entrypoint.

Public routes (`app.routers.public`) ARE the published contract and appear in the
committed `openapi.json`. Admin routes (`app.routers.admin`) are mounted under `/admin`
with separate auth and are excluded from the exported client contract (see
`scripts/export_openapi.py`).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import admin, public

app = FastAPI(
    title="set-embassy",
    summary="The online backend for SET.crawl — run ingest, daily challenge, personal bests.",
    version="0.1.0",
)

app.include_router(public.router)
app.include_router(admin.router)
