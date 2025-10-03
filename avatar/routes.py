"""Blueprint with endpoints for managing avatar configurations."""
from __future__ import annotations

from collections.abc import Iterable as IterableABC
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import Blueprint, abort, jsonify, request

from auth import authenticate_request, current_user_context, require_user_access

from . import repository
from .repository import (
    AvatarNotFoundError,
    AvatarQuotaExceededError,
    DuplicateAvatarNameError,
)

avatar_bp = Blueprint("avatar", __name__, url_prefix="/api")

# Maximum number of avatars returned from list endpoint.
_LIST_LIMIT = 5


# ---------------------------------------------------------------------------
# Authentication hooks
# ---------------------------------------------------------------------------


@avatar_bp.before_request
def _enforce_authentication():
    """Ensure requests hitting the avatar blueprint are authenticated."""

    authenticate_request()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_measurements(section: Optional[Dict[str, Any]], *, section_name: str) -> Dict[str, float]:
    if section is None:
        return {}
    if not isinstance(section, dict):
        abort(400, description=f"{section_name} must be an object of numeric values.")

    normalized: Dict[str, float] = {}
    for key, value in section.items():
        if not isinstance(key, str):
            abort(400, description=f"Measurement keys in {section_name} must be strings.")
        if not isinstance(value, (int, float)):
            abort(400, description=f"Measurement '{key}' in {section_name} must be a number.")
        normalized[key] = float(value)
    return normalized


def _iter_morph_items(payload: Any) -> Iterable[Tuple[str, float]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        iterable = payload.items()
    elif isinstance(payload, IterableABC) and not isinstance(payload, (str, bytes)):
        iterable = []
        for entry in payload:
            if isinstance(entry, dict):
                morph_id = entry.get("id")
                value = entry.get("value")
                iterable.append((morph_id, value))
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                iterable.append((entry[0], entry[1]))
            else:
                abort(400, description="Morph targets must be objects with 'id' and 'value'.")
    else:
        abort(400, description="Morph targets must be provided as an object or list of objects.")
        return []

    normalized_items: List[Tuple[str, float]] = []
    for morph_id, value in iterable:
        if morph_id is None:
            abort(400, description="Morph targets require an 'id'.")
        if not isinstance(morph_id, str):
            morph_id = str(morph_id)
        if not isinstance(value, (int, float)):
            abort(400, description=f"Morph target '{morph_id}' value must be numeric.")
        normalized_items.append((morph_id, float(value)))
    return normalized_items


def _normalize_morph_targets(payload: Any) -> List[Dict[str, Any]]:
    items = list(_iter_morph_items(payload))
    collapsed: Dict[str, float] = {}
    for morph_id, value in items:
        collapsed[morph_id] = value

    return [
        {"id": morph_id, "value": value}
        for morph_id, value in sorted(collapsed.items(), key=lambda pair: pair[0])
    ]


def _apply_payload(
    user_id: str,
    payload: Dict[str, Any],
    *,
    avatar_id: Optional[str] = None,
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        abort(400, description="Request payload must be a JSON object.")

    name = payload.get("name")
    if name is not None and not isinstance(name, str):
        abort(400, description="Avatar name must be a string.")

    basic_measurements = _normalize_measurements(
        payload.get("basicMeasurements"), section_name="basicMeasurements"
    )
    body_measurements = _normalize_measurements(
        payload.get("bodyMeasurements"), section_name="bodyMeasurements"
    )
    morph_targets = _normalize_morph_targets(payload.get("morphTargets"))

    avatar_name = name if isinstance(name, str) else ""

    try:
        if avatar_id is None:
            avatar = repository.create_avatar(
                user_id,
                name=avatar_name,
                basic_measurements=basic_measurements,
                body_measurements=body_measurements,
                morph_targets=morph_targets,
                user_context=user_context,
            )
        else:
            avatar = repository.update_avatar(
                user_id,
                avatar_id,
                name=avatar_name,
                basic_measurements=basic_measurements,
                body_measurements=body_measurements,
                morph_targets=morph_targets,
                user_context=user_context,
            )
    except DuplicateAvatarNameError as exc:
        abort(409, description=str(exc))
    except AvatarQuotaExceededError as exc:
        abort(409, description=str(exc))
    except AvatarNotFoundError as exc:
        abort(404, description=str(exc))
    except ValueError:
        abort(400, description="Avatar identifier is invalid.")
    return avatar

def _require_user_scope(user_id: str) -> None:
    """Abort the request when the authenticated user differs from ``user_id``."""

    require_user_access(user_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@avatar_bp.route("/users/<user_id>/avatars", methods=["GET"])
def list_avatars(user_id: str):
    _require_user_scope(user_id)
    user_context = current_user_context()
    response = repository.list_avatars(
        user_id,
        limit=_LIST_LIMIT,
        user_context=user_context,
    )
    return jsonify(response)


@avatar_bp.route("/users/<user_id>/avatars", methods=["POST"])
def create_avatar(user_id: str):
    _require_user_scope(user_id)
    user_context = current_user_context()
    payload = request.get_json(silent=True)
    if payload is None:
        abort(400, description="Request body must contain JSON data.")

    avatar = _apply_payload(user_id, payload, user_context=user_context)
    return jsonify(avatar), 201


@avatar_bp.route("/users/<user_id>/avatars/<avatar_id>", methods=["GET"])
def get_avatar(user_id: str, avatar_id: str):
    _require_user_scope(user_id)
    try:
        avatar = repository.get_avatar(user_id, avatar_id)
    except AvatarNotFoundError as exc:
        abort(404, description=str(exc))
    except ValueError:
        abort(400, description="Avatar identifier is invalid.")
    return jsonify(avatar)


@avatar_bp.route("/users/<user_id>/avatars/<avatar_id>", methods=["PUT"])
def update_avatar(user_id: str, avatar_id: str):
    _require_user_scope(user_id)
    user_context = current_user_context()
    payload = request.get_json(silent=True)
    if payload is None:
        abort(400, description="Request body must contain JSON data.")

    avatar = _apply_payload(
        user_id,
        payload,
        avatar_id=avatar_id,
        user_context=user_context,
    )
    return jsonify(avatar)