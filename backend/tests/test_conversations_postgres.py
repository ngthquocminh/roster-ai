from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text

from adapters.postgres.conversation import PostgresConversationRepository
from adapters.postgres.schema import agent_run, app_user, conversation, message, organization, persisted_event, scenario, scenario_version, site
from application.use_cases.accept_turn import accept_turn

pytestmark = pytest.mark.postgres


def _seed(engine):
    ids = {name: uuid4() for name in ("org", "site", "other_site", "scenario", "version", "actor")}
    with engine.begin() as c:
        c.execute(insert(organization).values(id=ids["org"], name="Org"))
        c.execute(insert(site), [{"id": ids["site"], "organization_id": ids["org"], "name": "A"}, {"id": ids["other_site"], "organization_id": ids["org"], "name": "B"}])
        c.execute(insert(app_user).values(id=ids["actor"], idp_subject="planner", email="planner@example.test"))
        c.execute(insert(scenario).values(id=ids["scenario"], site_id=ids["site"], fixture_id="fixture", name="Fixture"))
        c.execute(insert(scenario_version).values(id=ids["version"], site_id=ids["site"], scenario_id=ids["scenario"], fixture_id="fixture", version="v1", payload={}, checksum_digest="a" * 64))
    return ids


def _scoped(engine, site_id):
    connection = engine.connect(); transaction = connection.begin()
    connection.execute(text("SELECT set_config('app.site_id', :site, true)"), {"site": str(site_id)})
    connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
    return connection, transaction


def test_accept_turn_is_atomic_and_concurrent_sequences_are_unique(governed_postgres_engine) -> None:
    engine = governed_postgres_engine; ids = _seed(engine); repo = PostgresConversationRepository()
    c, tx = _scoped(engine, ids["site"]); created = repo.create(c, scenario_id=ids["scenario"], site_id=ids["site"], actor_id=ids["actor"]); tx.commit(); c.close(); assert created

    c, tx = _scoped(engine, ids["site"])
    with pytest.raises(RuntimeError):
        accept_turn(repo, c, conversation_id=created.id, site_id=ids["site"], actor_id=ids["actor"], text="rollback", after_message=lambda: (_ for _ in ()).throw(RuntimeError("injected")))
    tx.rollback(); c.close()
    with engine.connect() as admin:
        assert admin.execute(select(func.count()).select_from(message)).scalar_one() == 0

    def send(value: str) -> str:
        cx, txn = _scoped(engine, ids["site"])
        try:
            result = accept_turn(repo, cx, conversation_id=created.id, site_id=ids["site"], actor_id=ids["actor"], text=value); txn.commit(); assert result; return result.sequence
        finally: cx.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        sequences = set(pool.map(send, ("one", "two")))
    assert sequences == {"1", "2"}
    with engine.connect() as admin:
        assert admin.execute(select(func.count()).select_from(message)).scalar_one() == 2
        assert admin.execute(select(func.count()).select_from(agent_run)).scalar_one() == 2
        assert admin.execute(select(func.count()).select_from(persisted_event)).scalar_one() == 2
        assert admin.execute(select(conversation.c.resource_version).where(conversation.c.id == created.id)).scalar_one() == 3
    c, tx = _scoped(engine, ids["other_site"])
    try:
        assert repo.timeline(c, conversation_id=created.id) is None
        assert accept_turn(repo, c, conversation_id=created.id, site_id=ids["other_site"], actor_id=ids["actor"], text="hidden") is None
    finally: tx.rollback(); c.close()
