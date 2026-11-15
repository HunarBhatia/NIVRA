"""The Alembic migrations must build the same schema the models describe."""

import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app.core.db import Base

BACKEND = Path(__file__).resolve().parents[1]


def test_migrations_match_models(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    env = {**__import__("os").environ, "NIVRA_DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env,
                   check=True, capture_output=True)
    insp = inspect(create_engine(url))
    migrated = set(insp.get_table_names()) - {"alembic_version"}
    assert migrated == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in table.columns}
