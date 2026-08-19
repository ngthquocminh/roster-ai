"""Mutation-denial proof for the governed Gate A surface.

Two kinds of proof live here, and the distinction matters:

* **Structural** — the scenario read surface exposes no write verb, and the
  read adapters carry no mutating SQL. These bound what *can* be reached.
* **Behavioural** — real write requests are issued and observed to be denied.

Until 2026-08-18 the behavioural half was missing: a third test asserted string
literals inside `evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json`,
which proved the file had not been hand-edited and nothing whatsoever about the
running system. It is replaced below by requests that actually hit the app.

The write surface under test is Story 3.1's proposal aggregate. Its existence is
not a Gate A regression — see `docs/GATE-A-RUNBOOK.md`, "What 'read-only' means
once drafts are writable": a proposal is new state, never a mutation of
`scenario`/`scenario_version`.

What Gate A requires of a write route is that it is authenticated and
CSRF-guarded — enforced centrally for the whole `/api/v1` surface and asserted
per-route below. Site scoping is asserted separately and is deliberately NOT
uniform: `auth/logout` has no site-scoped row to protect, `agent-runs/execute`
opens its RLS connection inside the background run, and only the two proposal
write routes take `get_site_context` per request. Claiming one rule for all six
would be a comfortable sentence that no test could back.
"""
from __future__ import annotations

import ast
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import (
    get_identity_store,
    get_projection_reader,
    get_proposal_repository,
    get_settings,
    get_site_context,
)
from api.main import app
from application.ports.session import ResolvedSession
from settings import default_settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_READ_ADAPTERS = (
    BACKEND_ROOT / "adapters" / "postgres" / "scenario_projection.py",
    BACKEND_ROOT / "adapters" / "postgres" / "scenario_catalogue.py",
)
MUTATING_SQL_VERBS = ("INSERT", "UPDATE", "DELETE")


def test_gate_a_scenario_openapi_surface_is_get_only() -> None:
    scenario_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/scenarios")
    }

    assert scenario_paths
    for path, operations in scenario_paths.items():
        methods = set(operations) - {"parameters"}
        assert methods == {"get"}, f"{path} exposes {sorted(methods)}"


def test_gate_a_postgres_read_adapters_contain_no_mutating_sql_literals() -> None:
    findings: list[str] = []
    for path in SCENARIO_READ_ADAPTERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            upper = node.value.upper()
            for verb in MUTATING_SQL_VERBS:
                if verb in upper:
                    findings.append(f"{path.name}:{node.lineno} contains {verb}")

    assert findings == []


# --------------------------------------------------------------------------
# Behavioural denial: real write requests, really refused.
# --------------------------------------------------------------------------

_CSRF_TOKEN = "gate-a-csrf-token"
_SESSION_TOKEN = "gate-a-session-token"
_UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
#: Mirrors `api.main._PUBLIC_VERSIONED_PATHS`. Deliberately re-declared rather
#: than imported: if someone widens that set, this list stays narrow and the
#: parametrization below starts asserting denial on the newly-public path,
#: which is exactly the alarm we want. The reverse direction — an unsafe method
#: appearing on a path that is ALREADY public — would be invisible to that
#: filter, so it is closed separately by
#: `test_public_versioned_paths_expose_no_write_verb`.
_PUBLIC_VERSIONED_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/callback",
        "/api/v1/auth/session",
    }
)
#: Pre-Gate-A SQLite routes, still mounted outside `/api/v1`. They are
#: unauthenticated and site-unaware; what keeps them offline is
#: `refuse_legacy_routes_during_gate_a`, a filesystem-flag check rather than an
#: authorization check. Listed here so the write-surface assertion below covers
#: the WHOLE app — a test named "the write surface is exactly the approved
#: paths" that silently ignored three open write routes would be worse than no
#: test. Their live flag state is an operational fact, owned by
#: `docs/GATE-A-RUNBOOK.md` section 2, not by this suite.
_LEGACY_WRITE_ROUTES = (
    ("POST", "/constraints"),
    ("POST", "/scenarios"),
    ("POST", "/scenarios/{scenario_id}/runs"),
)


class _RecordingProposalRepository:
    """Records every call and performs none of them.

    A denied request must not reach data access at all, so any method landing
    here is itself the finding. `get_current` returning ``None`` keeps the
    authorized-path shape honest without inventing a proposal.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _record(self, name: str) -> None:
        self.calls.append(name)

    def create_draft(self, *_args: Any, **_kwargs: Any) -> None:
        self._record("create_draft")
        raise AssertionError("a denied request reached create_draft")

    def append_revision(self, *_args: Any, **_kwargs: Any) -> None:
        self._record("append_revision")
        raise AssertionError("a denied request reached append_revision")

    def reject(self, *_args: Any, **_kwargs: Any) -> None:
        self._record("reject")
        raise AssertionError("a denied request reached reject")

    def get_current(self, *_args: Any, **_kwargs: Any) -> None:
        self._record("get_current")
        return None

    def get_idempotent_result(self, *_args: Any, **_kwargs: Any) -> None:
        self._record("get_idempotent_result")
        return None


def _versioned_write_routes() -> list[tuple[str, str]]:
    """Every mutating route the app actually exposes under `/api/v1`.

    Read from the generated OpenAPI document, never from a hand-maintained
    list, so a write route added by a future story is covered the moment it is
    mounted. `app.routes` is not usable here: included routers appear as
    `_IncludedRouter` wrappers whose nested paths carry no `/api/v1` prefix.
    """
    found: list[tuple[str, str]] = []
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/v1/") or path in _PUBLIC_VERSIONED_PATHS:
            continue
        for method in operations:
            if method.upper() in _UNSAFE_METHODS:
                found.append((method.upper(), path))
    return sorted(found)


def _all_write_routes() -> list[tuple[str, str]]:
    """Every mutating route in the app, versioned or not."""
    found: list[tuple[str, str]] = []
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in _UNSAFE_METHODS:
                found.append((method.upper(), path))
    return sorted(found)


def _concrete(path: str) -> str:
    """Fill path templates with syntactically valid identifiers.

    Substitutes every `{...}` marker wherever it sits, not only whole segments:
    `/x/v{n}` and `/{a}-{b}` are legal FastAPI templates, and leaving their
    braces in place would send a URL-encoded literal that matches no route.
    Denial happens in middleware, before routing, so such a request would still
    return 401/403 and the test would pass against a path that does not exist.
    """
    return re.sub(r"\{[^}]+\}", lambda _match: str(uuid4()), path)


@pytest.fixture
def gate_a_write_client(tmp_path, monkeypatch):
    """The app with proposal storage stubbed, so only the transport is tested.

    `db_path` and `maintenance_flag_path` are set through the ENVIRONMENT, not
    only through `dependency_overrides`: `lifespan` calls module-level
    `get_settings()` (`api/main.py:45`) and so does `_gate_a_flag_is_set`
    (`api/main.py:132`), and neither consults overrides. Setting them on the
    injected `Settings` alone leaves both reading the real
    `backend/var/rosterai.db`, which is isolation in name only.
    """
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))
    monkeypatch.setenv(
        "ROSTERAI_MAINTENANCE_FLAG", str(tmp_path / "gate-a-maintenance")
    )
    resolved = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    class _IdentityStore:
        def resolve_session(self, token_hash: str) -> ResolvedSession | None:
            return resolved if token_hash == hash_secret(_SESSION_TOKEN) else None

    settings = replace(default_settings())
    repository = _RecordingProposalRepository()

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _IdentityStore()
    app.dependency_overrides[get_site_context] = lambda: object()
    app.dependency_overrides[get_proposal_repository] = lambda: repository
    app.dependency_overrides[get_projection_reader] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client, repository, settings
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_gate_a_write_surface_is_exactly_the_approved_paths() -> None:
    """The whole app's write surface, enumerated — legacy routes included.

    Not an allowlist that silences the guard: the three denial tests below run
    over whatever `_versioned_write_routes()` discovers, including routes added
    after this literal. This one exists so a new write path cannot land without
    a human recording in `docs/GATE-A-RUNBOOK.md` why it does not touch
    governed scenario data or the baseline pointer.

    It deliberately covers the un-versioned legacy routes too. They are NOT
    session-guarded — nothing here claims they are — but a "write surface"
    assertion that quietly skipped them would read as a clean bill of health
    over three open write paths.
    """
    versioned = [
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/conversations"),
        (
            "POST",
            "/api/v1/conversations/{conversation_id}"
            "/agent-runs/{agent_run_id}/execute",
        ),
        ("POST", "/api/v1/conversations/{conversation_id}/messages"),
        ("POST", "/api/v1/proposals/{proposal_id}/rejection"),
        ("POST", "/api/v1/proposals/{proposal_id}/revisions"),
    ]

    assert _versioned_write_routes() == versioned
    assert _all_write_routes() == sorted(versioned + list(_LEGACY_WRITE_ROUTES))


def test_public_versioned_paths_expose_no_write_verb() -> None:
    """Closes the blind spot in the `_PUBLIC_VERSIONED_PATHS` filter.

    `_versioned_write_routes()` skips public paths, so an unsafe method added
    to one would drop out of the denial parametrization unnoticed. Public means
    "reachable without a session" — it must never also mean "writable".
    """
    paths = app.openapi()["paths"]
    for public in sorted(_PUBLIC_VERSIONED_PATHS):
        methods = {m.upper() for m in paths.get(public, {})}
        assert not methods & set(_UNSAFE_METHODS), (
            f"{public} is exempt from session enforcement and exposes "
            f"{sorted(methods & set(_UNSAFE_METHODS))}"
        )


@pytest.mark.parametrize("method,path", _versioned_write_routes())
def test_every_versioned_write_route_denies_a_request_without_a_session(
    gate_a_write_client, method: str, path: str
) -> None:
    client, repository, _ = gate_a_write_client

    response = client.request(
        method,
        _concrete(path),
        json={},
        headers={"Idempotency-Key": "gate-a-denied"},
    )

    assert response.status_code == 401, f"{method} {path} was not denied"
    assert response.json()["code"] == "authentication_required"
    assert repository.calls == []


@pytest.mark.parametrize("method,path", _versioned_write_routes())
def test_every_versioned_write_route_denies_a_request_without_a_csrf_token(
    gate_a_write_client, method: str, path: str
) -> None:
    client, repository, settings = gate_a_write_client

    response = client.request(
        method,
        _concrete(path),
        json={},
        headers={
            "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
            "Origin": settings.app_base_url,
            "Idempotency-Key": "gate-a-denied",
        },
    )

    assert response.status_code == 403, f"{method} {path} was not denied"
    assert response.json()["code"] == "csrf_validation_failed"
    assert repository.calls == []


@pytest.mark.parametrize("method,path", _versioned_write_routes())
def test_every_versioned_write_route_denies_a_cross_origin_request(
    gate_a_write_client, method: str, path: str
) -> None:
    client, repository, _ = gate_a_write_client

    response = client.request(
        method,
        _concrete(path),
        json={},
        headers={
            "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
            "Origin": "https://attacker.example",
            "X-CSRF-Token": _CSRF_TOKEN,
            "Idempotency-Key": "gate-a-denied",
        },
    )

    assert response.status_code == 403, f"{method} {path} was not denied"
    assert response.json()["code"] == "csrf_validation_failed"
    assert repository.calls == []


def test_proposal_write_routes_resolve_site_context_and_session() -> None:
    """Site scoping is structural here; PostgreSQL RLS proves it behaviourally.

    A `TestClient` with a stubbed repository cannot demonstrate that another
    site's proposal is invisible — faking the repository would make the test
    assert its own stub, which is the circularity this file was cleaned of.
    What it *can* prove is that neither write handler can run without
    `get_site_context` (which sets `app.site_id` for RLS) and `get_session`
    (which supplies the site and actor). `test_proposal_persistence.py` owns
    the PostgreSQL side.
    """
    from api.deps import get_session

    # Included routers keep their un-prefixed paths; the `/api/v1` prefix is
    # applied by the include context, so match on the router-local path.
    write_paths = {
        "/proposals/{proposal_id}/revisions",
        "/proposals/{proposal_id}/rejection",
    }
    checked = 0
    for included in app.routes:
        router = getattr(included, "original_router", None)
        if router is None:
            continue
        for route in router.routes:
            if getattr(route, "path", "") not in write_paths:
                continue
            calls = {
                dependency.call for dependency in route.dependant.dependencies
            }
            assert get_site_context in calls, f"{route.path} is not site-scoped"
            assert get_session in calls, f"{route.path} resolves no session"
            checked += 1

    assert checked == len(write_paths)


def test_proposal_creating_run_route_is_site_scoped() -> None:
    """`agent-runs/{id}/execute` writes the proposal aggregate too.

    It is the route `finalize_agent_run` runs behind, so it creates proposals —
    yet it was outside the assertion above, which hardcoded the two
    `/proposals/...` paths. It scopes differently on purpose: the RLS-bound
    connection is opened inside the background run, so it depends on
    `get_site_context_opener` rather than on `get_site_context` per request.
    Asserted separately rather than folded in, because collapsing the two would
    mean accepting either dependency on either route.
    """
    from api.deps import get_session, get_site_context_opener

    target = "/conversations/{conversation_id}/agent-runs/{agent_run_id}/execute"
    checked = 0
    for included in app.routes:
        router = getattr(included, "original_router", None)
        if router is None:
            continue
        for route in router.routes:
            if getattr(route, "path", "") != target:
                continue
            calls = {d.call for d in route.dependant.dependencies}
            assert get_site_context_opener in calls, f"{target} is not site-scoped"
            assert get_session in calls, f"{target} resolves no session"
            checked += 1

    assert checked == 1


def test_an_authorized_proposal_write_does_reach_the_repository(
    gate_a_write_client,
) -> None:
    """Positive control for the three denial tests.

    Without this, `assert repository.calls == []` is true by construction:
    `enforce_versioned_session_and_csrf` short-circuits before routing, so a
    denied request never resolves `get_proposal_repository` at all. A middleware
    that rejected *everything* would leave every denial test green. This proves
    the requests are otherwise well-formed and that the recorder is wired in, so
    the empty-call-list assertions mean something.
    """
    client, repository, settings = gate_a_write_client

    response = client.post(
        f"/api/v1/proposals/{uuid4()}/rejection",
        json={"expected_resource_version": 1},
        headers={
            "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
            "Origin": settings.app_base_url,
            "X-CSRF-Token": _CSRF_TOKEN,
            "Idempotency-Key": "gate-a-authorized",
        },
    )

    # 404: the stub reports no such proposal. The point is that the request got
    # past authentication, CSRF and routing into the use case.
    assert response.status_code == 404
    assert response.json()["code"] == "proposal_not_found"
    assert repository.calls, "an authorized write never reached the repository"


def test_openapi_document_hides_no_write_route() -> None:
    """Route discovery reads OpenAPI, so a route absent from it is invisible.

    `include_in_schema=False` would drop a write route out of every guard in
    this file at once. Cross-checked against a walk of the real route tree.
    """
    documented = {(m, p) for m, p in _all_write_routes()}

    walked: set[tuple[str, str]] = set()
    for included in app.routes:
        router = getattr(included, "original_router", None)
        candidates = router.routes if router is not None else [included]
        prefixes = (
            ["/api/v1", ""] if router is not None else [""]
        )
        for route in candidates:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", None) or set()
            unsafe = set(methods) & set(_UNSAFE_METHODS)
            if not unsafe or path.startswith("/openapi") or path == "/docs":
                continue
            for method in unsafe:
                # A router-local path is reachable under exactly one of its
                # possible prefixes; accept whichever the document agrees with.
                if not any((method, p + path) in documented for p in prefixes):
                    raise AssertionError(
                        f"{method} {path} exists but is absent from the "
                        "OpenAPI document, so no guard in this file sees it"
                    )
                walked.add(
                    next(
                        (method, p + path)
                        for p in prefixes
                        if (method, p + path) in documented
                    )
                )

    assert walked == documented
