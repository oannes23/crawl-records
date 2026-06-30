"""FastAPI application entrypoint.

Public routes (`app.routers.public`) ARE the published contract and appear in the
committed `openapi.json`. Admin routes (`app.routers.admin`) are mounted under `/admin`
with separate auth and are excluded from the exported client contract (see
`scripts/export_openapi.py`).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, public

app = FastAPI(
    title="set-embassy",
    summary="The online backend for SET.crawl — run ingest, daily challenge, personal bests.",
    version="0.1.0",
)

# Allow the browser game-client (a different origin in dev: Vite :5173) to call the
# API. Explicit origins from config — never "*". Bearer auth travels in the
# Authorization header (no cookies), so credentials are not enabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(public.router)
app.include_router(admin.router)
