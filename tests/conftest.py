import json

import pytest

from backend.app.auth import hash_password

_TEST_PASSWORD = "synthetic-test-password-2026"
_TEST_HASH = hash_password(_TEST_PASSWORD)


@pytest.fixture(autouse=True)
def configured_test_auth(monkeypatch):
    monkeypatch.setenv("HELMET_AUTH_SECRET", "synthetic-test-signing-secret-at-least-32-bytes")
    monkeypatch.setenv("HELMET_ACCESS_TOKEN_MINUTES", "30")
    monkeypatch.setenv("HELMET_BOOTSTRAP_USERS", json.dumps([
        {"username": "administrator-test", "password_hash": _TEST_HASH, "role": "administrator"},
        {"username": "supervisor-test", "password_hash": _TEST_HASH, "role": "supervisor"},
        {"username": "viewer-test", "password_hash": _TEST_HASH, "role": "viewer"},
    ]))


def authenticate(client, username="supervisor-test", password=_TEST_PASSWORD):
    result = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert result.status_code == 200, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


@pytest.fixture
def auth_headers():
    return authenticate
