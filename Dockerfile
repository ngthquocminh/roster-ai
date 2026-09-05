FROM ghcr.io/astral-sh/uv:0.10.8 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/
RUN uv sync --project backend --frozen --all-groups --no-install-project
COPY alembic.ini ./
COPY data/ data/
COPY backend/ backend/

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend" \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
