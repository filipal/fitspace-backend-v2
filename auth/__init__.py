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


def _issue_token(user_id: str) -> Dict[str, Any]:
    """Create a signed JWT for the specified user."""

    now = datetime.now(timezone.utc)
    expiration = now + _get_expiration_delta()
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
        "scope": ["avatars:read", "avatars:write"],
    }

    token = jwt.encode(payload, _get_secret_key(), algorithm=_get_algorithm())
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    headers = {"Authorization": f"Bearer {token}"}
    return {
        "token": token,
        "tokenType": "Bearer",
        "expiresIn": int(_get_expiration_delta().total_seconds()),
        "user": {"id": user_id},
        "headers": headers,
    }


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

    g.current_user = {
        "id": str(user_id),
        "scope": decoded.get("scope", []),
    }
    return g.current_user["id"]


def current_user_id() -> Optional[str]:
    """Return the identifier of the currently authenticated user."""

    if getattr(g, "current_user", None):
        return g.current_user["id"]
    return None


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