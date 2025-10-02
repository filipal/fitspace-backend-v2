"""Blueprint with endpoints for managing avatar configurations."""
from __future__ import annotations

import uuid
from collections.abc import Iterable as IterableABC
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, abort, jsonify, request

avatar_bp = Blueprint("avatar", __name__, url_prefix="/api")

# ---------------------------------------------------------------------------
# In-memory persistence
# ---------------------------------------------------------------------------

# The data store is a nested mapping of user IDs -> avatar ID -> avatar payload.
_AVATAR_STORE: Dict[str, Dict[str, Dict[str, Any]]] = {}

# Maximum number of avatars returned from list endpoint.
_LIST_LIMIT = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp string."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _get_user_store(user_id: str) -> Dict[str, Dict[str, Any]]:
    return _AVATAR_STORE.setdefault(user_id, {})


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


def _serialize_avatar(user_id: str, avatar_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": avatar_id,
        "userId": user_id,
        "name": payload.get("name", "Untitled Avatar"),
        "basicMeasurements": payload.get("basicMeasurements", {}),
        "bodyMeasurements": payload.get("bodyMeasurements", {}),
        "morphTargets": payload.get("morphTargets", []),
        "createdAt": payload.get("createdAt"),
        "updatedAt": payload.get("updatedAt"),
    }


def _require_avatar(user_id: str, avatar_id: str) -> Dict[str, Any]:
    store = _get_user_store(user_id)
    avatar = store.get(avatar_id)
    if avatar is None:
        abort(404, description="Avatar not found.")
    return avatar


def _apply_payload(user_id: str, payload: Dict[str, Any], *, avatar_id: Optional[str] = None) -> Dict[str, Any]:
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

    store = _get_user_store(user_id)

    if avatar_id is None:
        avatar_id = str(uuid.uuid4())
        created_at = _current_timestamp()
    else:
        created_at = _require_avatar(user_id, avatar_id).get("createdAt", _current_timestamp())

    timestamp = _current_timestamp()
    avatar_name = name if isinstance(name, str) and name.strip() else "Untitled Avatar"

    avatar_payload = {
        "name": avatar_name,
        "basicMeasurements": basic_measurements,
        "bodyMeasurements": body_measurements,
        "morphTargets": morph_targets,
        "createdAt": created_at,
        "updatedAt": timestamp,
    }

    store[avatar_id] = avatar_payload
    return _serialize_avatar(user_id, avatar_id, avatar_payload)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@avatar_bp.route("/users/<user_id>/avatars", methods=["GET"])
def list_avatars(user_id: str):
    store = _get_user_store(user_id)
    serialized = [
        _serialize_avatar(user_id, avatar_id, payload)
        for avatar_id, payload in sorted(
            store.items(), key=lambda item: (item[1].get("createdAt") or "", item[0])
        )
    ]
    items = serialized[:_LIST_LIMIT]
    response = {
        "userId": user_id,
        "limit": _LIST_LIMIT,
        "count": len(items),
        "total": len(serialized),
        "items": items,
    }
    return jsonify(response)


@avatar_bp.route("/users/<user_id>/avatars", methods=["POST"])
def create_avatar(user_id: str):
    payload = request.get_json(silent=True)
    if payload is None:
        abort(400, description="Request body must contain JSON data.")

    avatar = _apply_payload(user_id, payload)
    return jsonify(avatar), 201


@avatar_bp.route("/users/<user_id>/avatars/<avatar_id>", methods=["GET"])
def get_avatar(user_id: str, avatar_id: str):
    payload = _require_avatar(user_id, avatar_id)
    return jsonify(_serialize_avatar(user_id, avatar_id, payload))


@avatar_bp.route("/users/<user_id>/avatars/<avatar_id>", methods=["PUT"])
def update_avatar(user_id: str, avatar_id: str):
    payload = request.get_json(silent=True)
    if payload is None:
        abort(400, description="Request body must contain JSON data.")

    avatar = _apply_payload(user_id, payload, avatar_id=avatar_id)
    return jsonify(avatar)