"""Local bearer authentication primitives; replaceable by an external IdP adapter."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pwdlib import PasswordHash

Role = Literal["administrator", "supervisor", "viewer"]
ALGORITHM = "HS256"
ISSUER = "smart-safety-helmet-local"
_password_hash = PasswordHash.recommended()
_dummy_hash = _password_hash.hash("dummy-password-for-timing-only")
_bearer = HTTPBearer(auto_error=False)


class BootstrapUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Annotated[str, Field(min_length=3, max_length=128)]
    password_hash: Annotated[str, Field(min_length=20, max_length=512)]
    role: Role

    @field_validator("password_hash")
    @classmethod
    def require_argon2id_hash(cls, value: str) -> str:
        if not value.startswith("$argon2id$"):
            raise ValueError("password_hash must be an Argon2id hash, not a plaintext password")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Annotated[str, Field(min_length=1, max_length=128)]
    password: SecretStr


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user_id: str
    role: Role


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role


class AuthenticationUnavailable(RuntimeError):
    pass


class LocalAuthService:
    """Verifies bootstrap hash records and signs expiring access tokens."""
    def __init__(self, secret: str, users: list[BootstrapUser], lifetime_minutes: int = 30):
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("HELMET_AUTH_SECRET must contain at least 32 bytes")
        if not users or len({u.username for u in users}) != len(users):
            raise ValueError("bootstrap users must be non-empty and usernames unique")
        self._secret = secret
        self._users = {user.username: user for user in users}
        self._lifetime = timedelta(minutes=lifetime_minutes)

    @classmethod
    def from_environment(cls) -> "LocalAuthService":
        secret = os.environ.get("HELMET_AUTH_SECRET", "")
        raw_users = os.environ.get("HELMET_BOOTSTRAP_USERS", "")
        if not secret or not raw_users:
            raise AuthenticationUnavailable("authentication configuration is missing")
        try:
            value = json.loads(raw_users)
            if not isinstance(value, list):
                raise ValueError("expected a JSON array")
            users = [BootstrapUser.model_validate(item) for item in value]
            lifetime = int(os.environ.get("HELMET_ACCESS_TOKEN_MINUTES", "30"))
            if not 1 <= lifetime <= 1440:
                raise ValueError("token lifetime must be between 1 and 1440 minutes")
            return cls(secret, users, lifetime)
        except (ValueError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise AuthenticationUnavailable("authentication configuration is invalid") from exc

    def login(self, username: str, password: str) -> LoginResponse | None:
        user = self._users.get(username)
        candidate_hash = user.password_hash if user else _dummy_hash
        try:
            valid = _password_hash.verify(password, candidate_hash)
        except (ValueError, TypeError):
            valid = False
        if user is None or not valid:
            return None
        now = datetime.now(timezone.utc)
        expires = now + self._lifetime
        token = jwt.encode(
            {"iss": ISSUER, "sub": user.username, "role": user.role,
             "iat": now, "exp": expires, "jti": os.urandom(16).hex()},
            self._secret, algorithm=ALGORITHM,
        )
        return LoginResponse(access_token=token, expires_at=expires,
                             user_id=user.username, role=user.role)

    def authenticate(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[ALGORITHM], issuer=ISSUER,
                                options={"require": ["exp", "iat", "sub", "role", "iss"]})
            role = claims["role"]
            if role not in {"administrator", "supervisor", "viewer"}:
                raise jwt.InvalidTokenError("invalid role")
            return Principal(user_id=claims["sub"], role=role)
        except (jwt.PyJWTError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="invalid or expired bearer token",
                                headers={"WWW-Authenticate": "Bearer"}) from exc


def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=401, detail="authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    auth: LocalAuthService | None = getattr(request.app.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=503, detail="authentication is not configured")
    return auth.authenticate(credentials.credentials)


def require_roles(*roles: Role):
    def dependency(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=403, detail="insufficient permissions")
        return principal
    return dependency


def hash_password(password: str) -> str:
    return _password_hash.hash(password)
