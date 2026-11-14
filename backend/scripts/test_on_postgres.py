"""Runs the migrations and the full test suite on a real, temporary PostgreSQL.

Needs the dev-only packages:  pip install pgserver "psycopg[binary]"
Run from backend/:            .venv/Scripts/python scripts/test_on_postgres.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pgserver
import psycopg

BACKEND = Path(__file__).resolve().parents[1]


def main() -> int:
    data = Path(tempfile.mkdtemp(prefix="nivra-pg-"))
    srv = pgserver.get_server(data, cleanup_mode="delete")
    try:
        # (pgserver's own psql() helper breaks on paths with spaces, so use psycopg.)
        with psycopg.connect(srv.get_uri(), autocommit=True) as conn:
            conn.execute("CREATE DATABASE nivra_migrations")
            conn.execute("CREATE DATABASE nivra_tests")
        base = srv.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)
        uri = lambda db: base.rsplit("/", 1)[0] + f"/{db}"  # swap only the database name  # noqa: E731
        env = {**os.environ}

        print("== migrations on PostgreSQL")
        mig = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND,
                             env={**env, "NIVRA_DATABASE_URL": uri("nivra_migrations")})
        if mig.returncode:
            return mig.returncode
        check = subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=BACKEND,
                               env={**env, "NIVRA_DATABASE_URL": uri("nivra_migrations")})
        if check.returncode:
            return check.returncode

        print("== test suite on PostgreSQL")
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", *sys.argv[1:]],
                              cwd=BACKEND,
                              env={**env, "NIVRA_TEST_DATABASE_URL": uri("nivra_tests")}).returncode
    finally:
        srv.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
