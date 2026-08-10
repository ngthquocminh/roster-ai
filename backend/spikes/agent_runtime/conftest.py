"""Make the spike root importable and forbid network access for the whole suite.

Mirrors backend/conftest.py's sys.path.insert trick so `import owned` resolves
regardless of the process CWD.

The ALLOW_MODEL_REQUESTS kill switch is set here AND at module scope in the test
file. That redundancy is deliberate: this spike's entire value is that its seven
verdicts are reproducible without a network or an API key, and a single missed
assignment would silently turn a capability proof into a live provider call.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from pydantic_ai import models  # noqa: E402

models.ALLOW_MODEL_REQUESTS = False
