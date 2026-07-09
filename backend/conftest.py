"""Make the backend package root importable when running pytest from anywhere."""
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

# Surface ONLY GEMINI_API_KEY from a local backend/.env so the @pytest.mark.live
# gate can detect a developer's key. Deliberately do NOT load LLM_PROVIDER /
# LLM_MODEL from .env — the test suite must observe the keyless `stub` default
# regardless of a developer's .env (stub-only-CI invariant). A real shell env
# var still wins (we only set the key when it is not already present).
_env_file = Path(__file__).resolve().parent / ".env"
_dotenv = dotenv_values(_env_file) if _env_file.exists() else {}
_gemini_key = _dotenv.get("GEMINI_API_KEY")
if _gemini_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = _gemini_key

sys.path.insert(0, os.path.dirname(__file__))

# settings.py runs its OWN load_dotenv(backend/.env) at import time (a real app
# requirement so the API server / run.py CLI honor a developer's .env). Left
# alone that import would leak LLM_PROVIDER / LLM_MODEL from a dev's .env into
# the test process and flip the default provider under test — breaking the
# stub-only-CI invariant. Trigger that one-time import here, then drop the
# leaked provider/model selection so every test observes the keyless `stub`
# default. This scoping is test-process only; the real app is unaffected, and
# GEMINI_API_KEY (surfaced above) is preserved for the @pytest.mark.live gate.
import settings as _settings  # noqa: E402,F401  (imported for its load_dotenv side effect)

os.environ.pop("LLM_PROVIDER", None)
os.environ.pop("LLM_MODEL", None)
