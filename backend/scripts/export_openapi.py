"""Export the FastAPI app's OpenAPI schema to a JSON file.

Feeds the frontend's type generation (`openapi-typescript`), so
`frontend/src/api/schema.d.ts` is always generated from the backend's own,
mechanically-derived schema rather than hand-typed from `docs/API.md`. Needs
no running server and touches no database: `app` is built at module level in
`api.main`, and `db.init_db` only runs inside the app's `lifespan` context
manager, which this script never enters.

Usage (from `backend/`):
    uv run python scripts/export_openapi.py [output_path]

`output_path` defaults to `../frontend/openapi.json` (relative to this
script's own directory, not the process CWD — resolved from `__file__` for
the same reason `settings.py` resolves `backend/.env` that way: the script
must work regardless of where it is invoked from).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Running `python scripts/export_openapi.py` puts `backend/scripts/` on
# sys.path[0], not `backend/` — so `from api.main import app` would fail with
# a bare ImportError that looks like a missing dependency. Insert the
# `scripts/` directory's parent (`backend/`) at the front of sys.path before
# importing, mirroring what `conftest.py` does for pytest.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from api.main import app  # noqa: E402  (import after sys.path fixup, by necessity)


def main() -> None:
    default_output = _BACKEND_DIR.parent / "frontend" / "openapi.json"
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_output

    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
