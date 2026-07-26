"""Make the backend package root importable when running pytest from anywhere."""
import os
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

# Surface ONLY GEMINI_API_KEY / OPENROUTER_API_KEY from a local backend/.env so
# the @pytest.mark.live gate can detect a developer's key. Deliberately do NOT
# load LLM_PROVIDER / LLM_MODEL / OPENROUTER_MODEL from .env — the test suite
# must observe the keyless `stub` default regardless of a developer's .env
# (stub-only-CI invariant). A real shell env var still wins (we only set the
# key when it is not already present).
_env_file = Path(__file__).resolve().parent / ".env"
_dotenv = dotenv_values(_env_file) if _env_file.exists() else {}
_gemini_key = _dotenv.get("GEMINI_API_KEY")
if _gemini_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = _gemini_key
_openrouter_key = _dotenv.get("OPENROUTER_API_KEY")
if _openrouter_key and not os.environ.get("OPENROUTER_API_KEY"):
    os.environ["OPENROUTER_API_KEY"] = _openrouter_key

sys.path.insert(0, os.path.dirname(__file__))

# settings.py runs its OWN load_dotenv(backend/.env) at import time (a real app
# requirement so the API server / run.py CLI honor a developer's .env). Left
# alone that import would leak LLM_PROVIDER / LLM_MODEL from a dev's .env into
# the test process and flip the default provider under test — breaking the
# stub-only-CI invariant. Trigger that one-time import here, then drop the
# leaked provider/model selection so every test observes the keyless `stub`
# default. This scoping is test-process only; the real app is unaffected, and
# GEMINI_API_KEY (surfaced above) is preserved for the @pytest.mark.live gate.
import settings as _settings  # noqa: E402,F401  (imported for its load_dotenv side effect)

os.environ.pop("LLM_PROVIDER", None)
os.environ.pop("LLM_MODEL", None)


@contextmanager
def _temporary_postgres_database():
    """Yield an isolated database URL and force-drop it after the test."""
    base_url = make_url(_settings.default_settings().provisioning_database_url)
    database_name = f"rosterai_test_{uuid4().hex}"
    admin_engine = create_engine(
        base_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    try:
        try:
            with admin_engine.connect() as connection:
                connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        except OperationalError:
            pytest.skip("PostgreSQL integration service is not available")
        yield base_url.set(database=database_name).render_as_string(
            hide_password=False
        )
    finally:
        try:
            with admin_engine.connect() as connection:
                connection.exec_driver_sql(
                    f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'
                )
        except OperationalError as exc:
            warnings.warn(
                f"Failed to drop throwaway test database {database_name!r}: {exc}"
            )
        admin_engine.dispose()


@pytest.fixture(scope="module")
def governed_postgres_engine():
    """Provide a migrated, throwaway PostgreSQL database for integration tests."""
    with _temporary_postgres_database() as database_url:
        engine = create_engine(database_url)
        config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        try:
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            yield engine
        finally:
            engine.dispose()


@pytest.fixture
def fresh_postgres_database_url():
    """Provide an unmigrated throwaway database for migration round-trip tests."""
    with _temporary_postgres_database() as database_url:
        yield database_url
