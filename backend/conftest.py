"""Make the backend package root importable when running pytest from anywhere."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before any test module is collected so a key placed only
# in .env (not the real OS env) makes _HAS_KEY true in test modules and
# enables the `-m live` test. override=False: a real OS env var still wins.
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

sys.path.insert(0, os.path.dirname(__file__))
