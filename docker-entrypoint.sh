#!/bin/sh
# Container entrypoint: bring the schema to head, then serve.
#
# `alembic upgrade head` is idempotent — on a fresh volume it creates the SQLite DB and all
# tables; on an existing one it applies any new migrations and is a no-op when already current.
# Single-instance by design (SQLite); do not scale this container horizontally without first
# moving to Postgres (EMBASSY_DATABASE_URL) and a migration-runner that won't race.
set -eu

echo "==> alembic upgrade head"
alembic upgrade head

echo "==> starting uvicorn on 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
