"""Read only owned, structured usage records from a disposable API container."""
import json
import re
import subprocess

from evals.live_conversations.protocol import IncompleteConversationRun


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
        if len(terminal) != 1 or terminal[0]['usage'] is None or terminal[0]['estimated_cost_usd'] is None:
            raise IncompleteConversationRun('application_usage_or_cost_unavailable')
        return terminal[0], [r for r in records if r['event'] == 'agent.tool.call.completed']
