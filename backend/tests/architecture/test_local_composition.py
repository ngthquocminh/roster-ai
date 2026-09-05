from __future__ import annotations

import ast
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
    assert "uv sync --project backend --frozen --all-groups" in backend
    assert "npm ci" in web
    assert "npm install" not in web
    assert "ARG VITE_API_BASE_URL" in web
