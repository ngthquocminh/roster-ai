from urllib.parse import parse_qs, urlparse
import base64
import hashlib

from fastapi.testclient import TestClient

from api.deps import get_settings
from api.main import app


def _challenge(verifier: str) -> str:
    """The S256 challenge for `verifier`, as a real client would compute it."""
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def _authorize_params(**overrides) -> dict[str, str]:
    params = {
        "client_id": "shiftmind-local",
        "code_challenge": _challenge("compose-proof-verifier"),
        "code_challenge_method": "S256",
        "nonce": "nonce",
        # The registered value, not an arbitrary one -- see the rejection test.
        "redirect_uri": get_settings().oidc_redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": "state",
    }
    params.update(overrides)
    return params


def test_fake_authorize_mints_a_code_and_redirects_to_callback() -> None:
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get(
            "/oidc/authorize", params=_authorize_params(), follow_redirects=False
        )
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["state"] == ["state"]
    assert query["code"][0].startswith("fake-")


def test_fake_authorize_refuses_an_unregistered_redirect_uri() -> None:
    """Without this the endpoint is an open redirect that leaks a live code.

    Every other parameter is valid, so the 400 can only come from the
    `redirect_uri` check.
    """
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get(
            "/oidc/authorize",
            params=_authorize_params(redirect_uri="https://attacker.example/collect"),
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert "redirect_uri" in response.json()["detail"]


def test_fake_authorize_percent_encodes_the_state_it_reflects() -> None:
    """A raw `&` in `state` would otherwise inject a parameter into the callback."""
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get(
            "/oidc/authorize",
            params=_authorize_params(state="a&code=injected"),
            follow_redirects=False,
        )
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["state"] == ["a&code=injected"]
    assert query["code"] == [query["code"][0]]
    assert not query["code"][0].startswith("injected")


def test_fake_jwks_is_served() -> None:
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/oidc/jwks")
    assert response.status_code == 200
    assert response.json()["keys"][0]["kid"] == "shiftmind-fake-key"


def test_fake_token_endpoint_consumes_pkce_code() -> None:
    verifier = "compose-proof-verifier"
    with TestClient(app, base_url="http://localhost") as client:
        authorize = client.get(
            "/oidc/authorize",
            params=_authorize_params(code_challenge=_challenge(verifier)),
            follow_redirects=False,
        )
        code = parse_qs(urlparse(authorize.headers["location"]).query)["code"][0]
        response = client.post(
            "/oidc/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": "shiftmind-local",
            },
        )
    assert response.status_code == 200
    assert response.json()["token_type"] == "Bearer"
    assert response.json()["id_token"]


def test_fake_token_endpoint_rejects_a_non_utf8_body() -> None:
    """A malformed body is a 400, never an unhandled decode error."""
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post("/oidc/token", content=b"\xff\xfe\x00grant_type=x")
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_grant"}


def test_local_oidc_write_route_stays_visible_to_the_write_surface_audit() -> None:
    """The inverse of what it looks like: these MUST be in the document.

    `test_openapi_document_hides_no_write_route` discovers routes by reading
    the OpenAPI document, so `include_in_schema=False` on `POST /oidc/token`
    would remove it from every Gate A write-surface guard at once.
    `docs/GATE-A-RUNBOOK.md` names it as an approved exception instead.
    """
    paths = app.openapi()["paths"]
    assert "/oidc/token" in paths
    assert "post" in paths["/oidc/token"]
