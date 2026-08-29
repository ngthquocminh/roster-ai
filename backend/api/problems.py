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
    body = {
            "type": f"https://shiftmind.app/problems/{code}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
        }
    if extra:
        body.update(extra)
    return JSONResponse(
        body,
        status_code=status,
        media_type="application/problem+json",
    )
