"""Read only owned, structured usage records from a disposable API container."""
import json
import re
import subprocess

from evals.live_conversations.protocol import IncompleteConversationRun

def failure_exception_type(log_text, agent_run_id):
    """Exception CLASS chain logged for one failed run -- never its message.

    The API logs JSON lines (`adapters/telemetry/json_logs.py`). The route's
    `execute_agent_turn failed` record carries `exception_type` (qualnames only)
    but no run id, and it is written before that run's own
    `agent.run.completed` record. Runs execute one at a time per isolated
    stack, so the nearest preceding failure record belongs to this run.
    """
    last_failure = None
    for line in log_text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if record.get('event') == 'agent.run.completed':
            if record.get('correlation', {}).get('agent_run_id') == agent_run_id:
                return last_failure
            last_failure = None
        elif (str(record.get('event', '')).startswith('execute_agent_turn failed')
                and isinstance(record.get('exception_type'), list)):
            last_failure = [str(name) for name in record['exception_type']]
    return None


class ContainerTelemetry:
    def __init__(self, container):
        if not re.fullmatch(r'shiftmind-(?:live|story)-[a-z0-9-]+-api-1', container):
            raise ValueError('a disposable live-evaluation container is required')
        self.container = container

    def read_run(self, agent_run_id):
        result = subprocess.run(['docker', 'logs', '--tail', '10000', self.container],
                                 capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise IncompleteConversationRun('application_telemetry_unavailable')
        records = []
        for line in (result.stdout + '\n' + result.stderr).splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict) or record.get('correlation', {}).get('agent_run_id') != agent_run_id:
                continue
            if record.get('event') not in {'agent.run.completed', 'agent.tool.call.completed'}:
                continue
            # Explicit selection discards exception messages, provider payloads,
            # and any future logging fields that are not part of this protocol.
            records.append({key: record.get(key) for key in (
                'event', 'correlation', 'labels', 'usage', 'estimated_cost_usd', 'budget_outcome')})
        terminal = [r for r in records if r['event'] == 'agent.run.completed']
        if len(terminal) != 1:
            raise IncompleteConversationRun('application_usage_or_cost_unavailable')
        tools = [r for r in records if r['event'] == 'agent.tool.call.completed']
        # Captured for ANY failed turn, not only one whose usage went missing:
        # B5 failed with usage present, so its cause stayed invisible.
        if (terminal[0].get('labels') or {}).get('failure_reason'):
            terminal[0]['failure_exception_type'] = failure_exception_type(
                result.stdout + '
' + result.stderr, agent_run_id)
        if terminal[0]['usage'] is None or terminal[0]['estimated_cost_usd'] is None:
            # A failed run whose exception path lost its usage. Scored as a
            # failed turn by the caller, not an incomplete suite; the exception
            # CLASS is kept so the cause is diagnosable (lesson 18).
            terminal[0]['usage_unavailable'] = True
            terminal[0]['failure_exception_type'] = failure_exception_type(
                result.stdout + '\n' + result.stderr, agent_run_id)
        return terminal[0], tools
