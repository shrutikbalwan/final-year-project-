import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app.auth import ALGORITHM, ISSUER
from backend.app.main import create_app
from backend.app.storage.sqlite import SQLiteStorage
from conftest import authenticate

ROOT = __import__("pathlib").Path(__file__).parents[1]


@pytest.fixture
def auth_api(tmp_path):
    return TestClient(create_app(SQLiteStorage(tmp_path / "auth.sqlite3")))


def test_login_issues_signed_expiring_role_token(auth_api):
    response = auth_api.post("/api/v1/auth/login", json={
        "username": "supervisor-test", "password": "synthetic-test-password-2026",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "supervisor"
    claims = jwt.decode(body["access_token"], "synthetic-test-signing-secret-at-least-32-bytes",
                        algorithms=[ALGORITHM], issuer=ISSUER)
    assert claims["sub"] == "supervisor-test"
    assert claims["exp"] > claims["iat"]


def test_incorrect_credentials_return_401_without_secret_logging(auth_api, caplog):
    response = auth_api.post("/api/v1/auth/login", json={
        "username": "supervisor-test", "password": "wrong-secret-value",
    })
    assert response.status_code == 401
    assert "wrong-secret-value" not in caplog.text


@pytest.mark.parametrize("token", ["not-a-jwt", jwt.encode({
    "iss": ISSUER, "sub": "supervisor-test", "role": "supervisor",
    "iat": datetime.now(timezone.utc) - timedelta(hours=1),
    "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
}, "synthetic-test-signing-secret-at-least-32-bytes", algorithm=ALGORITHM)])
def test_invalid_and_expired_tokens_return_401(auth_api, token):
    response = auth_api.get("/api/v1/helmets", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_health_is_public_but_data_routes_require_authentication(auth_api):
    assert auth_api.get("/health").status_code == 200
    for method, path in [
        ("get", "/api/v1/helmets"), ("get", "/api/v1/telemetry"),
        ("get", "/api/v1/incidents"), ("get", "/api/v1/events"),
        ("get", "/api/v1/analytics/events"), ("get", "/api/v1/workplaces/profiles"),
    ]:
        assert getattr(auth_api, method)(path).status_code == 401, path
    schema = auth_api.get("/openapi.json").json()
    assert "security" in schema["paths"]["/api/v1/telemetry"]["post"]
    assert "security" not in schema["paths"]["/api/v1/auth/login"]["post"]


def test_viewer_can_read_but_cannot_acknowledge_or_ingest(auth_api):
    viewer_headers = authenticate(auth_api, "viewer-test")
    assert auth_api.get("/api/v1/helmets", headers=viewer_headers).status_code == 200
    example = json.loads((ROOT / "contracts/v1/examples/telemetry.valid.json").read_text())
    example["event_id"] = "synthetic-viewer-write-denied"
    assert auth_api.post("/api/v1/telemetry", json=example, headers=viewer_headers).status_code == 403
    assert auth_api.post("/api/v1/incidents/not-real/acknowledge",
                         json={"acknowledged_by": "viewer-test"}, headers=viewer_headers).status_code == 403


def test_supervisor_acknowledges_as_authenticated_identity(auth_api):
    supervisor = authenticate(auth_api)
    admin = authenticate(auth_api, "administrator-test")
    example = json.loads((ROOT / "contracts/v1/examples/telemetry.valid.json").read_text())
    example.update(event_id="synthetic-auth-ack-telemetry", device_id="synthetic-auth-helmet",
                   workplace_id="synthetic-auth-workplace")
    example["health"].update(device_id=example["device_id"], workplace_id=example["workplace_id"])
    assert auth_api.post("/api/v1/telemetry", json=example, headers=admin).status_code == 201
    incident = auth_api.get("/api/v1/incidents", headers=supervisor).json()["items"][0]
    missing_auth = auth_api.post(f"/api/v1/incidents/{incident['incident_id']}/acknowledge",
                                 json={"acknowledged_by": "forged-client-identity"})
    assert missing_auth.status_code == 401
    response = auth_api.post(f"/api/v1/incidents/{incident['incident_id']}/acknowledge",
                             json={"acknowledged_by": "forged-client-identity"}, headers=supervisor)
    assert response.status_code == 200
    assert response.json()["acknowledged_by"] == "supervisor-test"


def test_only_administrator_can_change_safety_rules(auth_api):
    profile = json.loads((ROOT / "tests/fixtures/workplace-profile-dashboard-e2e.json").read_text())["profiles"][0]
    path = f"/api/v1/workplaces/profiles/{profile['workplace_id']}"
    assert auth_api.put(path, json=profile).status_code == 401
    viewer = authenticate(auth_api, "viewer-test")
    supervisor = authenticate(auth_api)
    admin = authenticate(auth_api, "administrator-test")
    assert auth_api.put(path, json=profile, headers=viewer).status_code == 403
    assert auth_api.put(path, json=profile, headers=supervisor).status_code == 403
    allowed = auth_api.put(path, json=profile, headers=admin)
    assert allowed.status_code == 200
    assert auth_api.get("/api/v1/workplaces/profiles", headers=viewer).json()[0]["workplace_id"] == profile["workplace_id"]
    assert auth_api.put(path, json={**profile, "workplace_id": "mismatch"}, headers=admin).status_code == 422
