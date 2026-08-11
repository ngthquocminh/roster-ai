"""Versioned immutable scenario catalogue API contracts."""
from __future__ import annotations

import inspect
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME
from api.deps import (
    get_catalogue_reader,
    get_identity_store,
    get_settings,
    get_site_context,
)
from api.main import app
from api.routers import scenario_catalogue
from api.schemas import FixtureCatalogueEntryOut, ScenarioContextOut
from application.ports.scenario_catalogue import (
    FixtureCatalogueEntry,
    ScenarioContext,
)
from application.ports.session import ResolvedSession
from settings import default_settings


class _IdentityStore:
    def __init__(self, session: ResolvedSession) -> None:
        self.session = session

    def resolve_session(self, _token_hash: str) -> ResolvedSession:
        return self.session


class _Reader:
    def __init__(
        self,
        entries: tuple[FixtureCatalogueEntry, ...],
        contexts: dict[UUID, ScenarioContext],
    ) -> None:
        self.entries = entries
        self.contexts = contexts

    def list_fixture_versions(self, _connection):
        return self.entries

    def get_scenario_context(self, _connection, scenario_id):
        return self.contexts.get(scenario_id)


@pytest.fixture()
def catalogue_client(tmp_path):
    site_id = uuid4()
    scenario_id = uuid4()
    version_id = uuid4()
    imported_at = datetime(2026, 7, 24, tzinfo=timezone.utc)
    entry = FixtureCatalogueEntry(
        scenario_id=scenario_id,
        fixture_id="fixture-a",
        scenario_name="Fixture A",
        scenario_version_id=version_id,
        fixture_version="v1",
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        imported_at=imported_at,
        site_id=site_id,
    )
    context = ScenarioContext(
        scenario_name=entry.scenario_name,
        scenario_id=scenario_id,
        scenario_version_id=entry.scenario_version_id,
        fixture_version=entry.fixture_version,
        checksum_algorithm=entry.checksum_algorithm,
        checksum_schema_version=entry.checksum_schema_version,
        checksum_digest=entry.checksum_digest,
        site_id=site_id,
        baseline_schedule_version=None,
    )
    resolved = ResolvedSession(
        app_user_id=uuid4(),
        site_id=site_id,
        csrf_token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )
    reader = _Reader((entry,), {scenario_id: context})
    # Restore rather than clear on teardown, and do it in a finally: a failing
    # assertion propagates in at the yield, and a bare clear() after the with
    # block would leave these overrides installed on the module-global app for
    # the rest of the session.
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(resolved)
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_catalogue_reader] = lambda: reader
    try:
        with TestClient(app) as client:
            yield client, entry
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _authenticated_headers() -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE_NAME}=opaque-session"}


def test_catalogue_and_context_return_versioned_site_owned_contracts(
    catalogue_client,
) -> None:
    client, entry = catalogue_client

    catalogue = client.get(
        "/api/v1/scenarios",
        headers=_authenticated_headers(),
    )
    context = client.get(
        f"/api/v1/scenarios/{entry.scenario_id}",
        headers=_authenticated_headers(),
    )

    assert catalogue.status_code == 200
    assert catalogue.json() == [
        {
            "schema_version": "v1",
            "scenario_id": str(entry.scenario_id),
            "fixture_id": entry.fixture_id,
            "scenario_name": entry.scenario_name,
            "scenario_version_id": str(entry.scenario_version_id),
            "fixture_version": entry.fixture_version,
            "checksum_algorithm": entry.checksum_algorithm,
            "checksum_schema_version": entry.checksum_schema_version,
            "checksum_digest": entry.checksum_digest,
            "imported_at": entry.imported_at.isoformat().replace("+00:00", "Z"),
            "site_id": str(entry.site_id),
        }
    ]
    assert context.status_code == 200
    assert context.json() == {
        "schema_version": "v1",
        "scenario_name": entry.scenario_name,
        "scenario_id": str(entry.scenario_id),
        "scenario_version_id": str(entry.scenario_version_id),
        "fixture_version": entry.fixture_version,
        "checksum_algorithm": entry.checksum_algorithm,
        "checksum_schema_version": entry.checksum_schema_version,
        "checksum_digest": entry.checksum_digest,
        "site_id": str(entry.site_id),
        "baseline_schedule_version": None,
    }


@pytest.mark.parametrize(
    "path",
    ["/api/v1/scenarios", f"/api/v1/scenarios/{uuid4()}"],
)
def test_catalogue_paths_without_session_are_non_disclosing(path: str) -> None:
    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 401
    # Assert the whole body, not the absence of a few sample phrases: an
    # exact match is what actually proves no fixture, scenario, site, or
    # membership field leaked into the unauthenticated response.
    assert response.json() == {
        "type": "https://shiftmind.app/problems/authentication_required",
        "title": "Authentication required",
        "status": 401,
        "detail": "A valid application session is required.",
        "code": "authentication_required",
    }


def test_database_failure_stays_within_the_problem_details_contract(
    tmp_path,
) -> None:
    """A PostgreSQL outage must not escape to Starlette's text/plain 500 while
    the route advertises ProblemDetailsV1, and must disclose nothing."""

    def _explode():
        raise RuntimeError(
            "connection to server at 'db.internal' (10.0.0.5) failed"
        )

    settings = replace(
        default_settings(),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )
    resolved = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(resolved)
    app.dependency_overrides[get_site_context] = _explode
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/api/v1/scenarios",
                headers=_authenticated_headers(),
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "https://shiftmind.app/problems/internal_error",
        "title": "Internal server error",
        "status": 500,
        "detail": "The request could not be completed.",
        "code": "internal_error",
    }
    assert "db.internal" not in response.text
    assert "10.0.0.5" not in response.text


def test_unknown_scenario_is_the_standard_non_disclosing_404(
    catalogue_client,
) -> None:
    client, _ = catalogue_client

    response = client.get(
        f"/api/v1/scenarios/{uuid4()}",
        headers=_authenticated_headers(),
    )

    assert response.status_code == 404
    assert response.json() == {
        "type": "https://shiftmind.app/problems/resource_not_found",
        "title": "Resource not found",
        "status": 404,
        "detail": "The requested resource was not found.",
        "code": "resource_not_found",
    }


def test_catalogue_exposes_only_get_in_routes_and_openapi() -> None:
    unsafe = {"POST", "PUT", "PATCH", "DELETE"}
    matching_routes = []
    for route in app.routes:
        included_router = getattr(route, "original_router", None)
        prefix = getattr(getattr(route, "include_context", None), "prefix", "")
        candidates = (
            included_router.routes
            if included_router is not None
            else (route,)
        )
        matching_routes.extend(
            candidate
            for candidate in candidates
            if f"{prefix}{getattr(candidate, 'path', '')}".startswith(
                "/api/v1/scenarios"
            )
        )
    assert matching_routes
    assert all(not unsafe.intersection(route.methods or set()) for route in matching_routes)

    matching_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/scenarios")
    }
    assert matching_paths
    assert all(
        not {method.upper() for method in operations}.intersection(unsafe)
        for operations in matching_paths.values()
    )


@pytest.mark.parametrize(
    ("port_type", "response_model"),
    [
        (FixtureCatalogueEntry, FixtureCatalogueEntryOut),
        (ScenarioContext, ScenarioContextOut),
    ],
)
def test_response_models_carry_every_port_field(port_type, response_model) -> None:
    """A field added to a port dataclass must reach the wire. Pydantic ignores
    unknown keys, so without this the API would quietly keep the old shape."""
    port_fields = {field.name for field in fields(port_type)}
    model_fields = set(response_model.model_fields)

    assert port_fields <= model_fields
    # schema_version is contributed by the contract, not the port.
    assert model_fields - port_fields == {"schema_version"}


def test_catalogue_handlers_are_sync_for_the_synchronous_database_engine() -> None:
    assert not inspect.iscoroutinefunction(
        scenario_catalogue.list_fixture_versions
    )
    assert not inspect.iscoroutinefunction(
        scenario_catalogue.get_scenario_context
    )
