"""Authentication utilities and endpoints for the Fitspace backend."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, Optional

import jwt
from flask import Blueprint, abort, current_app, g, jsonify, request

__all__ = [
    "auth_bp",
    "init_app",
    "authenticate_request",
    "require_user_access",
    "current_user_id",
    "current_user_context",
]


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _get_secret_key() -> str:
    secret = current_app.config.get("JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET is not configured. Call auth.init_app(app) during application setup."
        )
    return secret


def _get_algorithm() -> str:
    return current_app.config.get("JWT_ALGORITHM", "HS256")


def _get_expiration_delta() -> timedelta:
    seconds = int(current_app.config.get("JWT_EXP_SECONDS", 3600))
    return timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def init_app(app) -> None:
    """Initialise authentication configuration for the Flask app."""

    secret = app.config.get("JWT_SECRET") or os.getenv("JWT_SECRET")
    if not secret:
        secret = "change-me-in-production"
        app.logger.warning(
            "JWT_SECRET is not configured. Falling back to an insecure development secret."
        )

    app.config.setdefault("JWT_SECRET", secret)
    app.config.setdefault("JWT_ALGORITHM", "HS256")
    app.config.setdefault("JWT_EXP_SECONDS", 3600)
    app.config.setdefault("AUTH_API_KEY", os.getenv("AUTH_API_KEY"))


# ---------------------------------------------------------------------------
# Token handling
# ---------------------------------------------------------------------------


def _issue_token(
    user_id: str,
    *,
    email: Optional[str] = None,
    session_id: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a signed JWT for the specified user."""

    now = datetime.now(timezone.utc)
    expiration = now + _get_expiration_delta()
    payload: Dict[str, Any] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
        "scope": ["avatars:read", "avatars:write"],
    }

    if email:
        payload["email"] = email
    if session_id:
        payload["sid"] = session_id
    if refresh_token:
        payload["refreshToken"] = refresh_token

    token = jwt.encode(payload, _get_secret_key(), algorithm=_get_algorithm())
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    headers = {"Authorization": f"Bearer {token}"}
    if email:
        headers["X-User-Email"] = email
    if session_id:
        headers["X-Session-Id"] = session_id
    if refresh_token:
        headers["X-Refresh-Token"] = refresh_token

    response: Dict[str, Any] = {
        "token": token,
        "tokenType": "Bearer",
        "expiresIn": int(_get_expiration_delta().total_seconds()),
        "issuedAt": payload["iat"],
        "expiresAt": payload["exp"],
        "user": {"id": user_id},
        "headers": headers,
    }

    if email:
        response["user"]["email"] = email
    if session_id:
        response["sessionId"] = session_id
    if refresh_token:
        response["refreshToken"] = refresh_token

    return response

# ---------------------------------------------------------------------------
# Blueprint routes
# ---------------------------------------------------------------------------


@auth_bp.route("/token", methods=["POST"])
def create_token():
    """Issue a JWT for the provided user identifier."""

    payload = request.get_json(silent=True) or {}

    user_id = payload.get("userId") or payload.get("user_id")
    if not user_id or not isinstance(user_id, str):
        abort(400, description="Request payload must include a string 'userId'.")

    api_key = payload.get("apiKey")
    expected_key = current_app.config.get("AUTH_API_KEY")
    if expected_key and api_key != expected_key:
        abort(401, description="Provided API key is invalid.")

    token_response = _issue_token(user_id)
    email = payload.get("email")
    if email is not None and not isinstance(email, str):
        abort(400, description="If provided, 'email' must be a string.")

    session_id = payload.get("sessionId") or payload.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        abort(400, description="If provided, 'sessionId' must be a string.")

    refresh_token = payload.get("refreshToken") or payload.get("refresh_token")
    if refresh_token is not None and not isinstance(refresh_token, str):
        abort(400, description="If provided, 'refreshToken' must be a string.")

    token_response = _issue_token(
        user_id,
        email=email,
        session_id=session_id,
        refresh_token=refresh_token,
    )
    return jsonify(token_response)


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def authenticate_request() -> str:
    """Validate the bearer token in the request and populate ``g.current_user``."""

    if getattr(g, "current_user", None):
        return g.current_user["id"]

    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        abort(401, description="Authorization header must contain a Bearer token.")

    try:
        decoded = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=[_get_algorithm()],
        )
    except jwt.ExpiredSignatureError:
        abort(401, description="Authentication token has expired.")
    except jwt.InvalidTokenError:
        abort(401, description="Authentication token is invalid.")

    user_id = decoded.get("sub")
    if not user_id:
        abort(401, description="Authentication token is missing a subject (user).")

    header_email = request.headers.get("X-User-Email") or decoded.get("email")
    if header_email is None:
        abort(400, description="Header 'X-User-Email' je obavezan za avatar API pozive.")

    session_id = request.headers.get("X-Session-Id") or decoded.get("sid") or decoded.get(
        "sessionId"
    )
    if not session_id:
        abort(400, description="Header 'X-Session-Id' je obavezan za avatar API pozive.")

    refresh_token = request.headers.get("X-Refresh-Token") or decoded.get("refreshToken")

    issued_at_value = decoded.get("iat")
    issued_at = (
        datetime.fromtimestamp(int(issued_at_value), tz=timezone.utc)
        if isinstance(issued_at_value, (int, float))
        else None
    )

    expires_at_value = decoded.get("exp")
    expires_at = (
        datetime.fromtimestamp(int(expires_at_value), tz=timezone.utc)
        if isinstance(expires_at_value, (int, float))
        else None
    )

    g.current_user = {
        "id": str(user_id),
        "scope": decoded.get("scope", []),
        "email": str(header_email),
        "session_id": str(session_id),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "access_token": token,
        "refresh_token": refresh_token,
    }
    return g.current_user["id"]


def current_user_id() -> Optional[str]:
    """Return the identifier of the currently authenticated user."""

    if getattr(g, "current_user", None):
        return g.current_user["id"]
    return None

def current_user_context() -> Dict[str, Any]:
    """Return full authentication context for the current request."""

    if getattr(g, "current_user", None) is None:
        authenticate_request()
    return g.current_user

def require_user_access(user_id: str) -> None:
    """Ensure the authenticated user can access the provided ``user_id``."""

    authenticated_user = current_user_id()
    if authenticated_user is None:
        authenticated_user = authenticate_request()

    if authenticated_user != str(user_id):
        abort(403, description="You are not allowed to access resources for another user.")


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def requires_authentication(func):
    """Decorator to enforce authentication on view functions."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        authenticate_request()
        return func(*args, **kwargs)

    return wrapper