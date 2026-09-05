"""Local-only HTTP surface for the in-process fake OIDC provider."""
from __future__ import annotations

import os
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import JSONResponse, RedirectResponse

from adapters.oidc.fake import FakeOidcProvider
from api.deps import get_oidc_provider
from application.ports.identity import OidcProvider


router = APIRouter(prefix="/oidc", tags=["local-oidc"])


def _fake(provider: OidcProvider) -> FakeOidcProvider:
    if not isinstance(provider, FakeOidcProvider):
        raise HTTPException(status_code=404)
    return provider


@router.get("/authorize", status_code=302)
async def authorize(
    state: str,
    nonce: str,
    code_challenge: str,
    redirect_uri: str,
    client_id: str,
    response_type: str,
    code_challenge_method: str,
    provider: OidcProvider = Depends(get_oidc_provider),
) -> RedirectResponse:
    fake = _fake(provider)
    if client_id != fake.client_id or response_type != "code" or code_challenge_method != "S256":
        raise HTTPException(status_code=400, detail="invalid OIDC authorization request")
    subject = os.environ.get("SHIFTMIND_SEED_PLANNER_SUBJECT", "local-planner")
    email = os.environ.get("SHIFTMIND_SEED_PLANNER_EMAIL", "planner@shiftmind.local")
    code = fake.issue_authorization_code_from_challenge(
        subject=subject, email=email, nonce=nonce, code_challenge=code_challenge
    )
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}code={code}&state={state}", status_code=302)


@router.post("/token")
async def token(
    request: Request,
    provider: OidcProvider = Depends(get_oidc_provider),
) -> JSONResponse:
    form = parse_qs((await request.body()).decode("utf-8"))
    try:
        if form.get("grant_type", [None])[0] != "authorization_code":
            raise ValueError("unsupported grant type")
        payload = _fake(provider).exchange_code_for_token_response(
            code=form.get("code", [""])[0],
            code_verifier=form.get("code_verifier", [""])[0],
            client_id=form.get("client_id", [""])[0],
        )
    except ValueError:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    return JSONResponse(payload)


@router.get("/jwks")
async def jwks(provider: OidcProvider = Depends(get_oidc_provider)) -> dict[str, object]:
    return _fake(provider).jwks


__all__ = ["router"]
