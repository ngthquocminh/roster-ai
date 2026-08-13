"""FastAPI dependencies: settings, a per-request DB connection, and the engine.

`get_engine` is a seam: tests override it with a stub so the run lifecycle can
be exercised without a real (slow) solve.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Callable, ContextManager, Iterator
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Connection, Engine, create_engine as create_postgres_engine, text

from adapters.postgres.identity import PostgresIdentitySessionStore
from adapters.postgres.conversation import PostgresConversationRepository
from adapters.postgres.scenario_catalogue import PostgresScenarioCatalogueReader
from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from application.ports.identity import OidcProvider, create_provider as create_oidc_provider
from application.ports.conversation import ConversationRepository
from application.ports.scenario_catalogue import ScenarioCatalogueReader
from application.ports.scenario_projection import ScenarioProjectionReader
from application.capabilities.registry import (
    CapabilityGrantContextV1,
    compose_granted_capabilities,
)
from application.capabilities.module import CapabilityModuleV1
from application.ports.session import IdentitySessionStore, ResolvedSession
from engine.base import SchedulerEngine, create_engine
from llm.base import LLMProvider, create_provider
from settings import Settings, default_settings
from agent.runtime import create_agent_runtime
from store import db


def get_settings() -> Settings:
    return default_settings()


def get_db(settings: Settings = Depends(get_settings)) -> Iterator:
    conn = db.connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_engine() -> SchedulerEngine:
    return create_engine("cpsat")


def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return create_provider(settings.llm_provider, settings=settings)


@lru_cache(maxsize=8)
def _identity_store(database_url: str) -> PostgresIdentitySessionStore:
    return PostgresIdentitySessionStore(database_url)


def get_identity_store(
    settings: Settings = Depends(get_settings),
) -> IdentitySessionStore:
    return _identity_store(settings.database_url)


_catalogue_reader: ScenarioCatalogueReader = PostgresScenarioCatalogueReader()


def get_catalogue_reader() -> ScenarioCatalogueReader:
    """The catalogue read port. A seam, like `get_identity_store`: tests
    substitute an implementation through `dependency_overrides` rather than
    reaching into a router's module globals."""
    return _catalogue_reader


_projection_reader: ScenarioProjectionReader = PostgresScenarioProjectionReader()


def get_projection_reader() -> ScenarioProjectionReader:
    """Depends-overridable normalized scenario projection read port."""
    return _projection_reader


CapabilityComposer = Callable[
    [CapabilityGrantContextV1], tuple[CapabilityModuleV1, ...]
]
AgentRuntimeFactory = Callable[..., object]


def get_capability_registry() -> CapabilityComposer:
    """Depends-overridable application-owned capability composition seam.

    Returns the composer rather than a composed grant: the grant depends on
    per-run trusted context (role, site, feature policy, conversation) that only
    the caller holds. No route consumes this yet — Story 2.7 puts the first
    agent turn on a request path and finds the seam already shaped.
    """
    return compose_granted_capabilities


def get_agent_runtime_factory() -> AgentRuntimeFactory:
    """Depends-overridable constructor for one fully scoped agent runtime."""
    return create_agent_runtime


_conversation_repository: ConversationRepository = PostgresConversationRepository()


def get_conversation_repository() -> ConversationRepository:
    return _conversation_repository


@lru_cache(maxsize=8)
def _oidc_provider(
    name: str,
    issuer: str,
    client_id: str,
    client_secret: str | None,
) -> OidcProvider:
    class _ProviderSettings:
        oidc_issuer = issuer
        oidc_client_id = client_id
        oidc_client_secret = client_secret

    return create_oidc_provider(name, settings=_ProviderSettings())


def get_oidc_provider(
    settings: Settings = Depends(get_settings),
) -> OidcProvider:
    return _oidc_provider(
        settings.oidc_provider,
        settings.oidc_issuer,
        settings.oidc_client_id,
        settings.oidc_client_secret,
    )


async def get_session(
    request: Request,
    store: IdentitySessionStore = Depends(get_identity_store),
) -> ResolvedSession:
    """Re-resolve the current server-side session and active membership."""
    state_session = getattr(request.state, "shiftmind_session", None)
    if state_session is not None:
        return state_session
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    resolved = await run_in_threadpool(store.resolve_session, hash_secret(token))
    if resolved is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.shiftmind_session = resolved
    request.state.shiftmind_session_token = token
    return resolved


@lru_cache(maxsize=8)
def _site_context_engine(database_url: str) -> Engine:
    return create_postgres_engine(database_url)


@contextmanager
def site_context(engine: Engine, site_id: UUID | str) -> Iterator[Connection]:
    """Open one short site-scoped PostgreSQL transaction (AD-23).

    The single place in this repository that establishes trusted site context.
    Both callers go through it:

    * :func:`get_site_context`, the FastAPI dependency, whose transaction lives
      as long as the request.
    * Story 2.4's SSE stream, which calls this **directly**, once per poll,
      inside ``run_in_threadpool``. It must never take the dependency: that
      would pin one pooled connection inside an open transaction for the life of
      a stream measured in hours, and ``_site_context_engine``'s default pool
      (5 + 10 overflow) means roughly fifteen concurrent Chat tabs would consume
      every connection the application has — sign-in, Scenario Data and the
      timeline read all block, while the held connections sit ``idle in
      transaction`` pinning the oldest snapshot and blocking vacuum.
    """
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.site_id', :site_id, true)"),
            {"site_id": str(site_id)},
        )
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        try:
            yield connection
        finally:
            # If the transaction was already aborted by an exception raised
            # while the caller used `connection`, this cleanup statement
            # would itself raise InFailedSqlTransaction and mask the real
            # error — the surrounding `with engine.begin()` still rolls
            # back correctly either way, so swallow that specific failure.
            try:
                connection.execute(
                    text("SELECT set_config('app.site_id', '', true)")
                )
            except Exception:
                pass


def get_site_context(
    session: ResolvedSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Iterator[Connection]:
    """Yield the sole supported site-scoped PostgreSQL transaction."""
    engine = _site_context_engine(settings.database_url)
    with site_context(engine, session.site_id) as connection:
        yield connection


#: Opens one site-scoped transaction on demand. See `get_site_context_opener`.
SiteContextOpener = Callable[[UUID], ContextManager[Connection]]


def get_site_context_opener(
    settings: Settings = Depends(get_settings),
) -> SiteContextOpener:
    """A *factory* for site-scoped transactions — not a transaction.

    The SSE endpoint opens and closes one short transaction per poll and must
    therefore not take `get_site_context`, whose transaction lives as long as
    the request (see `site_context` for what that costs a long-lived stream).
    Depending on a factory keeps the same `dependency_overrides` seam every
    other port uses while opening nothing at request time.
    """
    engine = _site_context_engine(settings.database_url)

    def _open(site_id: UUID) -> ContextManager[Connection]:
        return site_context(engine, site_id)

    return _open
