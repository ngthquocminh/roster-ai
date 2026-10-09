from __future__ import annotations

import ast
import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def unguarded_fake_oidc_mounts(source: str) -> list[str]:
    tree = ast.parse(source)
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        condition = ast.unparse(node.test)
        if ".oidc_provider == 'fake'" not in condition and '.oidc_provider == "fake"' not in condition:
            continue
        guarded.update(id(child) for statement in node.body for child in ast.walk(statement))
    return [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func).endswith("include_router")
        and node.args
        and ast.unparse(node.args[0]) == "fake_oidc.router"
        and id(node) not in guarded
    ]


def test_fake_oidc_router_mount_is_provider_guarded() -> None:
    source = (BACKEND_ROOT / "api/main.py").read_text(encoding="utf-8")
    assert not unguarded_fake_oidc_mounts(source)


def test_fake_oidc_mount_guard_detects_synthetic_violation() -> None:
    assert unguarded_fake_oidc_mounts(
        "from api.routers import fake_oidc\napp.include_router(fake_oidc.router)"
    ) == ["app.include_router(fake_oidc.router)"]


def test_container_builds_use_frozen_dependency_paths() -> None:
    backend = (BACKEND_ROOT.parent / "Dockerfile").read_text(encoding="utf-8")
    web = (BACKEND_ROOT.parent / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --project backend --frozen --no-dev --no-install-project" in backend
    # `--all-groups` would install the dev group (pytest, pyyaml), which is
    # never shipped at runtime. An unfrozen install would satisfy AC2's words
    # and defeat it.
    assert "--all-groups" not in backend
    assert "uv sync" in backend and "--frozen" in backend
    assert "npm ci" in web
    assert "npm install" not in web
    assert "ARG VITE_API_BASE_URL" in web


def test_runtime_image_excludes_untracked_local_developer_state() -> None:
    """`COPY backend/ backend/` would otherwise bake `.env` and `var/` in.

    `settings.py` calls `load_dotenv(backend/.env, override=False)` at import,
    so a baked file supplies every key compose does not set — and it would make
    the recorded image digest depend on untracked local state.
    """
    ignored = {
        line.strip()
        for line in (BACKEND_ROOT.parent / ".dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert {".env", ".env.*", "**/.env", "**/.env.*", "**/var/", "*.db"} <= ignored


# Story 6.2 D10 / AR27: immutable digests own patch movement. A tag alone
# (`python:3.12-slim`) re-resolves to whatever was published last.
_PINNED_FROM = re.compile(r"^FROM\s+\S+:[^\s@]+@sha256:[0-9a-f]{64}(\s+AS\s+\S+)?\s*$", re.IGNORECASE)


def from_lines(dockerfile: str) -> list[str]:
    return [line.strip() for line in dockerfile.splitlines() if line.strip().upper().startswith("FROM ")]


def unpinned_from_lines(dockerfile: str) -> list[str]:
    return [line for line in from_lines(dockerfile) if not _PINNED_FROM.match(line)]


def test_every_container_base_is_pinned_by_tag_and_digest() -> None:
    for path in ("Dockerfile", "frontend/Dockerfile"):
        dockerfile = (BACKEND_ROOT.parent / path).read_text(encoding="utf-8")
        assert len(from_lines(dockerfile)) == 2, path
        assert unpinned_from_lines(dockerfile) == [], path


def test_base_digest_guard_detects_synthetic_violations() -> None:
    digest = "0" * 64
    assert unpinned_from_lines(
        "FROM python:3.12-slim\n"
        "FROM node:22@sha256:abc AS build\n"
        f"FROM nginx@sha256:{digest}\n"
        f"FROM python:3.12-slim@sha256:{digest}\n"
        f"FROM ghcr.io/astral-sh/uv:0.10.8@sha256:{digest} AS uv\n"
    ) == [
        "FROM python:3.12-slim",
        "FROM node:22@sha256:abc AS build",
        f"FROM nginx@sha256:{digest}",
    ]
