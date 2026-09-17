"""Read only owned, structured usage records from a disposable API container."""
import json
import re
import subprocess

from evals.live_conversations.protocol import IncompleteConversationRun

_EXCEPTION_LINE = re.compile(r'^([A-Za-z_][\w.]*(?:Error|Exception|Behavior|Exceeded|Warning))(?::|$)')


def failure_exception_type(log_text, agent_run_id):
    """Class name of the exception logged for one failed run -- never its message.

    The route logs `execute_agent_turn failed; finalizing run <id> as terminal`
    followed by a traceback whose last line is `module.Class: message`. Only the
    class name is returned; the message can quote model output.
    """
    lines = log_text.splitlines()
    marker = f'finalizing run {agent_run_id} as terminal'
    for start, line in enumerate(lines):
        if marker not in line:
            continue
        found = None
        for candidate in lines[start + 1:start + 400]:
            if candidate.lstrip().startswith('{'):
                break
            match = _EXCEPTION_LINE.match(candidate.strip())
            if match and not candidate.startswith((' ', '	')):
                found = match.group(1)
        return found
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
        if terminal[0]['usage'] is None or terminal[0]['estimated_cost_usd'] is None:
            # A failed run whose exception path lost its usage. Scored as a
            # failed turn by the caller, not an incomplete suite; the exception
            # CLASS is kept so the cause is diagnosable (lesson 18).
            terminal[0]['usage_unavailable'] = True
            terminal[0]['failure_exception_type'] = failure_exception_type(
                result.stdout + '\n' + result.stderr, agent_run_id)
        return terminal[0], tools
