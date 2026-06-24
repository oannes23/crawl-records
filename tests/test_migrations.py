"""Criterion 10 — Alembic migrations apply from empty and are reversible."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parent.parent


def _alembic_cfg(db_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_from_empty_then_downgrade(tmp_path, monkeypatch):
    db_file = tmp_path / "mig.db"
    db_url = f"sqlite:///{db_file}"
    # the env.py reads the URL from app settings → point it at the temp db
    monkeypatch.setenv("EMBASSY_DATABASE_URL", db_url)
    from app.config import get_settings

    get_settings.cache_clear()
    cfg = _alembic_cfg(db_url)

    # apply from empty
    command.upgrade(cfg, "head")
    insp = inspect(create_engine(db_url))
    tables = set(insp.get_table_names())
    assert {"identity", "run"}.issubset(tables)

    # reversible: back to empty (no app tables remain)
    command.downgrade(cfg, "base")
    insp = inspect(create_engine(db_url))
    remaining = set(insp.get_table_names()) - {"alembic_version"}
    assert remaining == set()

    get_settings.cache_clear()
