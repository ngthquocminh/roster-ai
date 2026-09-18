"""Real OIDC/CSRF conversation client used only by opt-in live evaluations."""
from __future__ import annotations

import math
import re
from time import monotonic, sleep
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from evals.live_conversations.protocol import IncompleteConversationRun


class ApplicationConversation:
    def __init__(self, origin: str, *, client: httpx.Client | None = None):
        self.origin = origin.rstrip('/')
        self.client = client or httpx.Client(follow_redirects=False, timeout=150)
        self.headers = {}
        self.conversation = None
        self.fixture = None

    def _request(self, method, path, *, body=None, expected=200, command=False):
        headers = dict(self.headers)
        if command:
            headers['Idempotency-Key'] = str(uuid4())
        try:
            response = self.client.request(method, self.origin + path, headers=headers, json=body)
        except httpx.HTTPError:
            raise IncompleteConversationRun('application_transport_unavailable') from None
        if response.status_code != expected:
            # Name the route (IDs masked, no response body) so a mid-scenario
            # failure is diagnosable after the disposable stack is gone.
            route = re.sub(r'[0-9a-fA-F-]{36}', '*', path.split('?')[0])
            raise IncompleteConversationRun(
                f'application_http_{response.status_code}_{method}_{route}')
        return response.json()

    def login(self):
        url = self.origin + '/api/v1/auth/login'
        for _ in range(3):
            if urlsplit(url).netloc != urlsplit(self.origin).netloc:
                raise IncompleteConversationRun('unexpected_login_origin')
            response = self.client.get(url)
            if response.status_code != 302:
                raise IncompleteConversationRun('authentication_failed')
            if '__Host-shiftmind_session=' in response.headers.get('set-cookie', ''):
                self.headers['Cookie'] = response.headers['set-cookie'].split(';', 1)[0]
                break
            url = response.headers['location']
        if 'Cookie' not in self.headers:
            raise IncompleteConversationRun('authentication_failed')
        session = self._request('GET', '/api/v1/auth/session')
        self.headers.update({'Origin': self.origin, 'X-CSRF-Token': session['csrf_token']})
        return session

    def create(self, fixture_name='sample_tiny_input'):
        fixtures = self._request('GET', '/api/v1/scenarios')
        self.fixture = next((item for item in fixtures if item['scenario_name'] == fixture_name), None)
        if self.fixture is None:
            raise IncompleteConversationRun('fixture_unavailable')
        self.conversation = self._request('POST', '/api/v1/conversations', expected=201, body={
            'scenario_id': self.fixture['scenario_id'],
            'scenario_version_id': self.fixture['scenario_version_id'],
        })
        return self.conversation

    def send(self, user):
        path = '/api/v1/conversations/' + self.conversation['id']
        accepted = self._request('POST', path + '/messages', body={'text': user}, expected=201)
        execute = path + '/agent-runs/' + accepted['agent_run_id'] + '/execute'
        try:
            executed = self._request('POST', execute)
        except IncompleteConversationRun as exc:
            # Seen twice in ~20 executions: execute answered 404 for a run the
            # immediately preceding 201 had just created. Retried once, briefly,
            # and the outcome is recorded either way -- a retry that succeeds
            # means the row was not yet visible to the next request, which is a
            # product finding; a retry that 404s again means it was never there.
            if not str(exc).startswith('application_http_404_POST'):
                raise
            sleep(1)
            try:
                executed = self._request('POST', execute)
            except IncompleteConversationRun:
                raise IncompleteConversationRun(str(exc) + '_still_missing_after_retry') from None
            accepted['execute_retried_after_404'] = True
        return accepted, executed

    def timeline(self):
        return self._request('GET', '/api/v1/conversations/' + self.conversation['id'] + '/timeline')

    def projection(self, group, *, limit=200, cursor=0):
        return self._request('GET', '/api/v1/scenarios/' + self.fixture['scenario_id']
                             + '/projection/' + group + f'?limit={limit}&cursor={cursor}')

    def latest_draft(self):
        """Resolve actual persisted draft identity; never synthesize model effects."""
        timeline = self.timeline()
        if timeline.get('has_more'):
            raise IncompleteConversationRun('timeline_truncated')
        drafts = [item for item in timeline['items'] if item['activity_type'] == 'draft']
        if not drafts:
            raise IncompleteConversationRun('required_draft_missing')
        proposal = self._request('GET', '/api/v1/proposals/' + drafts[-1]['proposal_id'])
        if proposal['state'] != 'active' or proposal['stale']:
            raise IncompleteConversationRun('required_draft_not_current')
        return proposal

    def run_optimization(self):
        proposal = self.latest_draft()
        return self._request('POST', '/api/v1/schedule-runs', command=True, body={
            'proposal_id': proposal['proposal_id'],
            'expected_resource_version': proposal['resource_version'],
        })

    def wait_for_run(self, run_id, *, timeout_seconds=120, max_polls=120):
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 600
                or type(max_polls) is not int or not 0 < max_polls <= 600):
            raise ValueError('positive bounded solver polling limits are required')
        deadline = monotonic() + timeout_seconds
        self.run_not_visible_polls = 0
        for _ in range(max_polls):
            if monotonic() >= deadline:
                break
            try:
                run = self._request('GET', '/api/v1/schedule-runs/' + run_id)
            except IncompleteConversationRun as exc:
                # The run was created moments ago and is not visible to this
                # request yet (live-suite-evidence-final aborted a whole run on
                # exactly this). Keep polling inside the existing bound rather
                # than failing the scenario; the count is reported.
                if not str(exc).startswith('application_http_404_GET'):
                    raise
                self.run_not_visible_polls += 1
                sleep(min(1, max(0, deadline - monotonic())))
                continue
            if run['status'] in {'solver_completed', 'solver_infeasible', 'solver_timed_out',
                                 'solver_cancelled', 'solver_failed'}:
                return self._request('GET', '/api/v1/schedule-runs/' + run_id + '/result')
            sleep(min(1, max(0, deadline - monotonic())))
        raise IncompleteConversationRun('solver_poll_budget_exhausted')

    def cancel_run(self, run):
        return self._request('POST', '/api/v1/schedule-runs/' + run['schedule_run_id']
                             + '/cancellation', command=True,
                             body={'expected_resource_version': run['resource_version']})

    def decide(self, approval_id, *, decision):
        if decision not in {'approve', 'reject'}:
            raise ValueError('explicit approve or reject decision required')
        approval = self._request('GET', '/api/v1/approvals/' + approval_id)
        if approval['state'] != 'pending':
            raise IncompleteConversationRun('required_pending_approval_missing')
        return self._request('POST', '/api/v1/approvals/' + approval_id + '/decision',
                             command=True, body={'decision': decision,
                             'expected_resource_version': approval['resource_version']})

    def reject_draft(self):
        proposal = self.latest_draft()
        return self._request('POST', '/api/v1/proposals/' + proposal['proposal_id'] + '/rejection',
                             command=True, body={'expected_resource_version': proposal['resource_version']})

    def close(self):
        self.client.close()
