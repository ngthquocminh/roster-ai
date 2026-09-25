FROM ghcr.io/astral-sh/uv:0.10.8 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/
# `--frozen` is what AC2 requires: install exactly what uv.lock pins, never
# re-resolve. `--no-dev` keeps backend/pyproject.toml's dev group out of the
# image: pytest, pyyaml, and the Logfire SDK and pydantic-evals (Story 5.10).
# Installed, the Logfire SDK would turn `logfire_api` into the real SDK inside
# the runtime. Nothing runs tests inside a container — the compose proof drives
# from the host — so the dev group has no runtime consumer here.
RUN uv sync --project backend --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY data/ data/
COPY backend/ backend/

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend" \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
