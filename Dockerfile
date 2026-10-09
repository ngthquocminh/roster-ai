FROM ghcr.io/astral-sh/uv:0.10.8@sha256:88234bc9e09c2b2f6d176a3daf411419eb0370d450a08129257410de9cfafd2a AS uv
FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

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
