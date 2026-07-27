"""Versioned immutable scenario catalogue API contracts."""
from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME
from api.deps import get_identity_store, get_settings, get_site_context
from api.main import app
from api.routers import scenario_catalogue
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
def catalogue_client(tmp_path, monkeypatch):
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
    monkeypatch.setattr(scenario_catalogue, "_reader", reader)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore(resolved)
    app.dependency_overrides[get_site_context] = lambda: object()
    with TestClient(app) as client:
        yield client, entry
    app.dependency_overrides.clear()


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
    assert response.json()["code"] == "authentication_required"
    body = response.text.lower()
    assert "fixture a" not in body
    assert "scenario name" not in body
    assert "site name" not in body
    assert "membership" not in body


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


def test_catalogue_handlers_are_sync_for_the_synchronous_database_engine() -> None:
    assert not inspect.iscoroutinefunction(
        scenario_catalogue.list_fixture_versions
    )
    assert not inspect.iscoroutinefunction(
        scenario_catalogue.get_scenario_context
    )
