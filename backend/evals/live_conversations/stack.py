"""Every prefix owns its Compose project and database volume."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep
from uuid import uuid4

import httpx

from evals.live_conversations.protocol import IncompleteConversationRun

ROOT = Path(__file__).resolve().parents[3]


def _stack_environment(*, origin, postgres_port, model, api_key, reasoning_effort,
                       demonstration_enabled):
    return {**os.environ, 'APP_ORIGIN': origin, 'WEB_PORT': '18097',
            'POSTGRES_PORT': str(postgres_port),
            'BACKEND_IMAGE': 'shiftmind-backend:live-conversation-eval',
            'WEB_IMAGE': 'shiftmind-web:live-conversation-eval',
            'AGENT_RUNTIME_MODEL': model, 'AGENT_RUNTIME_API_KEY': api_key,
            'AGENT_RUNTIME_REASONING_EFFORT': reasoning_effort,
            'DEMONSTRATION_ENABLED': str(demonstration_enabled).lower()}


def build_live_images(*, model, api_key, override_file, origin='http://localhost:18097',
                      reasoning_effort='low', demonstration_enabled=False):
    """Build once; each prefix still receives a fresh Compose project/volume."""
    env = _stack_environment(origin=origin, postgres_port=55497, model=model, api_key=api_key,
        reasoning_effort=reasoning_effort, demonstration_enabled=demonstration_enabled)
    command = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'),
               '-f', str(override_file), 'build', 'api', 'web']
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise IncompleteConversationRun('isolated_stack_build_failed') from None
    if result.returncode:
        raise IncompleteConversationRun('isolated_stack_build_failed')


@contextmanager
def isolated_stack(*, model, api_key, override_file, origin='http://localhost:18097', postgres_port=55497,
                   reasoning_effort='low', demonstration_enabled=False):
    if origin != 'http://localhost:18097' or postgres_port != 55497:
        raise ValueError('use the fixed isolated evaluation ports')
    project = 'shiftmind-live-' + uuid4().hex[:12]
    env = _stack_environment(origin=origin, postgres_port=postgres_port, model=model, api_key=api_key,
        reasoning_effort=reasoning_effort, demonstration_enabled=demonstration_enabled)
    command = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'),
               '-f', str(override_file), '-p', project]
    started = False
    try:
        # Both images are rebuilt under the fixed evaluation origin. Reusing a
        # web image compiled for another port would send API calls to that stack.
        started = True
        try:
            result = subprocess.run([*command, 'up', '-d', '--no-build'], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            raise IncompleteConversationRun('isolated_stack_start_failed') from None
        if result.returncode:
            raise IncompleteConversationRun('isolated_stack_start_failed')
        deadline = monotonic() + 60
        while monotonic() < deadline:
            try:
                if httpx.get(origin + '/health', timeout=3).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            sleep(1)
        else:
            raise IncompleteConversationRun('isolated_stack_not_ready')
        yield {'isolation_id': project, 'origin': origin, 'container': project + '-api-1',
               'database_url': f'postgresql+psycopg://shiftmind_login:shiftmind_login@localhost:{postgres_port}/rosterai'}
    finally:
        if started:
            # Generated here, never taken from caller input: teardown can only
            # affect this prefix's disposable project, including its own volume.
            try:
                result = subprocess.run([*command, 'down', '--volumes', '--remove-orphans'],
                                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
                cleanup_failed = bool(result.returncode)
            except subprocess.TimeoutExpired:
                cleanup_failed = True
            if cleanup_failed and sys.exc_info()[0] is None:
                # Only surface a cleanup failure when nothing else is already
                # propagating -- raising here would replace and hide the real
                # root cause (e.g. isolated_stack_start_failed).
                raise IncompleteConversationRun('isolated_stack_cleanup_failed')
