from urllib.parse import parse_qs, urlparse
import base64
import hashlib

from fastapi.testclient import TestClient

from api.main import app


def test_fake_authorize_mints_a_code_and_redirects_to_callback(monkeypatch) -> None:
    monkeypatch.setenv("SHIFTMIND_SEED_PLANNER_SUBJECT", "local-planner")
    monkeypatch.setenv("SHIFTMIND_SEED_PLANNER_EMAIL", "planner@shiftmind.local")
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get(
            "/oidc/authorize",
            params={
                "client_id": "shiftmind-local",
                "code_challenge": "challenge",
                "code_challenge_method": "S256",
                "nonce": "nonce",
                "redirect_uri": "http://localhost/api/v1/auth/callback",
                "response_type": "code",
                "scope": "openid email",
                "state": "state",
            },
            follow_redirects=False,
        )
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["state"] == ["state"]
    assert query["code"][0].startswith("fake-")


def test_fake_jwks_is_served() -> None:
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/oidc/jwks")
    assert response.status_code == 200
    assert response.json()["keys"][0]["kid"] == "shiftmind-fake-key"


def test_fake_token_endpoint_consumes_pkce_code() -> None:
    verifier = "compose-proof-verifier"
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    with TestClient(app, base_url="http://localhost") as client:
        authorize = client.get(
            "/oidc/authorize",
            params={
                "client_id": "shiftmind-local",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "nonce": "nonce",
                "redirect_uri": "http://localhost/api/v1/auth/callback",
                "response_type": "code",
                "state": "state",
            },
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
