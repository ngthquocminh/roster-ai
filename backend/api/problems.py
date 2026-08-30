"""Stable RFC 7807 responses shared by versioned API boundaries."""
from __future__ import annotations

from starlette.responses import JSONResponse


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    extra: dict | None = None,
) -> JSONResponse:
    # `extra` carries AD-13's literal expected/current context. It is merged
    # FIRST so the reserved RFC 7807 members always win: a caller passing
    # `status` here would otherwise publish a body disagreeing with the real
    # HTTP status code, which is the one thing a problem document may not do.
    body = dict(extra or {})
    body.update(
        {
            "type": f"https://shiftmind.app/problems/{code}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
        }
    )
    return JSONResponse(
        body,
        status_code=status,
        media_type="application/problem+json",
    )
