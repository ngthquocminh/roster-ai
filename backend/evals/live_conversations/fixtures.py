"""Real governed fixture setup, separate from evaluated conversation history."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine

from adapters.postgres.proposal import PostgresProposalRepository
from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_draft import SchedulingDraftRequestV1, scheduling_draft
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.proposal import DraftConstraintProposalV1
from evals.live_conversations.protocol import IncompleteConversationRun
from worker.lease_worker import runtime_context


def prepare_candidate(app, *, session, database_url, conversation_id):
    """Create a real proposal and feasible candidate for a specified conversation."""
    tasks = app.projection('work-areas-and-tasks')['items']
    if not tasks:
        raise IncompleteConversationRun('fixture_has_no_tasks')
    engine = create_engine(database_url, hide_parameters=True)
    site = UUID(session['site_id'])
    actor = UUID(session['app_user_id'])
    try:
        with runtime_context(engine, site) as connection:
            result = scheduling_draft(AgentDepsV1(actor_id=actor, site_id=site,
                membership_id=uuid4(), request_id=uuid4(), agent_run_id=uuid4(),
                conversation_id=UUID(conversation_id), scenario_id=UUID(app.fixture['scenario_id']),
                scenario_version_id=UUID(app.fixture['scenario_version_id']),
                policy_version='one-user-mvp-v1', clock=lambda: datetime.now(timezone.utc),
                projection_reader=PostgresScenarioProjectionReader(), connection=connection,
                remaining_budget=AgentBudgetV1()), SchedulingDraftRequestV1(
                    expected_scenario_version_id=UUID(app.fixture['scenario_version_id']), constraints=(
                    DraftConstraintProposalV1(kind='set_min_workers_per_task',
                        group='work-areas-and-tasks', record_id=tasks[0]['record_id'], n=1),)))
            proposal = PostgresProposalRepository().create_draft(connection,
                proposal=result.proposal, site_id=site, conversation_id=UUID(conversation_id), actor_id=actor)
    finally:
        engine.dispose()
    run = app._request('POST', '/api/v1/schedule-runs', command=True,
        body={'proposal_id': str(proposal.proposal_id), 'expected_resource_version': proposal.resource_version})
    terminal = app.wait_for_run(run['schedule_run_id'])
    if terminal['run']['status'] != 'solver_completed' or not terminal['candidate']:
        raise IncompleteConversationRun('fixture_seed_solve_not_feasible')
    return {'conversation_id': conversation_id, 'proposal_id': str(proposal.proposal_id),
            'proposal_resource_version': proposal.resource_version, 'run': terminal['run'],
            'candidate': terminal['candidate']}


def prepare_initial_baseline(app, *, session, database_url):
    """Seed an actual feasible baseline through existing draft/run/approval paths.

    Called in a dedicated setup conversation before the evaluated conversation
    exists. It inserts no assistant history and counts as fixture setup only.
    """
    setup = app.create()
    prepared = prepare_candidate(app, session=session, database_url=database_url,
                                 conversation_id=setup['id'])
    terminal = {'run': prepared['run'], 'candidate': prepared['candidate']}
    run = prepared['run']
    approval = app._request('POST', '/api/v1/approvals', command=True,
        body={'schedule_run_id': run['schedule_run_id'],
              'expected_resource_version': run['resource_version'],
              'expected_baseline_schedule_version': None})
    decision = app.decide(approval['approval_id'], decision='approve')
    if decision['state'] != 'consumed':
        raise IncompleteConversationRun('fixture_seed_approval_not_consumed')
    return {'kind': 'fixture_setup_not_conversation_evidence', 'conversation_id': setup['id'],
            'run': terminal['run'], 'candidate_schedule_version_id': terminal['candidate']['schedule_version_id'],
            'approval_id': approval['approval_id'], 'assignment_count': len(terminal['candidate']['assignments'])}
