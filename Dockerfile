FROM ghcr.io/astral-sh/uv:0.10.8 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/
# `--frozen` is what AC2 requires: install exactly what uv.lock pins, never
# re-resolve. `--no-dev` is what backend/pyproject.toml requires: its dev group
# carries `opentelemetry-sdk`, annotated "Deliberately in the dev group, never
# [project].dependencies: it is not shipped at runtime", plus pytest and httpx.
# Nothing runs tests inside a container — the compose proof drives from the
# host — so the dev group has no runtime consumer here.
RUN uv sync --project backend --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY data/ data/
COPY backend/ backend/

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend" \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
