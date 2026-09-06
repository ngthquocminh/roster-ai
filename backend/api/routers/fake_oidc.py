"""Local-only HTTP surface for the in-process fake OIDC provider."""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import JSONResponse, RedirectResponse

from adapters.oidc.fake import FakeOidcProvider
from api.deps import get_oidc_provider, get_settings
from application.ports.identity import OidcProvider
from settings import Settings


#: Deliberately IN the OpenAPI document, despite being dev-only.
#: `include_in_schema=False` was tried at code review and reverted:
#: `test_openapi_document_hides_no_write_route` exists precisely to stop a
#: write route disappearing from the document, because every Gate A
#: write-surface guard discovers routes by reading it. Hiding `POST
#: /oidc/token` would have dropped it out of all of them at once — the
#: opposite of `docs/GATE-A-RUNBOOK.md`'s choice to name this route so "the
#: exception remains visible". The cost is that `npm run codegen` emits
#: `/oidc/*` into the generated client; that is contract drift to manage, not
#: exposure to hide.
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
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    fake = _fake(provider)
    if client_id != fake.client_id or response_type != "code" or code_challenge_method != "S256":
        raise HTTPException(status_code=400, detail="invalid OIDC authorization request")
    # A real authorization server matches `redirect_uri` against a registered
    # value; without that this endpoint is an open redirect that hands a live
    # authorization code to any host the caller names.
    if redirect_uri != settings.oidc_redirect_uri:
        raise HTTPException(status_code=400, detail="invalid OIDC redirect_uri")
    code = fake.issue_authorization_code_from_challenge(
        subject=settings.seed_planner_subject,
        email=settings.seed_planner_email,
        nonce=nonce,
        code_challenge=code_challenge,
    )
    separator = "&" if "?" in redirect_uri else "?"
    query = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri}{separator}{query}", status_code=302)


@router.post("/token")
async def token(
    request: Request,
    provider: OidcProvider = Depends(get_oidc_provider),
) -> JSONResponse:
    try:
        # The decode belongs inside the guard: a non-UTF-8 body is a malformed
        # request, not a server fault, and must not surface as a 500.
        form = parse_qs((await request.body()).decode("utf-8"))
        if form.get("grant_type", [None])[0] != "authorization_code":
            raise ValueError("unsupported grant type")
        payload = _fake(provider).exchange_code_for_token_response(
            code=form.get("code", [""])[0],
            code_verifier=form.get("code_verifier", [""])[0],
            client_id=form.get("client_id", [""])[0],
        )
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    return JSONResponse(payload)


@router.get("/jwks")
async def jwks(provider: OidcProvider = Depends(get_oidc_provider)) -> dict[str, object]:
    return _fake(provider).jwks


__all__ = ["router"]
