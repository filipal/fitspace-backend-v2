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

_ALLOWED_GENDERS = {"female", "male", "non_binary", "unspecified"}
_AGE_RANGE_UI_LABELS = [
    "15-19",
    "20-29",
    "30-39",
    "40-49",
    "50-59",
    "60-69",
    "70-79",
    "80-89",
    "90-99",
]
_ALLOWED_AGE_RANGES = {
    "child",
    "teen",
    "young_adult",
    "adult",
    "mature",
    "senior",
    *{label.lower() for label in _AGE_RANGE_UI_LABELS},
}
_ALLOWED_CREATION_MODES = {"manual", "scan", "preset", "import"}
_ALLOWED_SOURCES = {"web", "ios", "android", "kiosk", "api", "integration"}
_MEASUREMENT_STATUS_KEYS = {"creationMode"}

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


def _normalize_enum(value: Optional[Any], *, field: str, allowed: set[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        abort(400, description=f"{field} must be a string.")
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        abort(400, description=f"{field} must be one of: {allowed_values}.")
    return normalized


def _normalize_optional_string(value: Optional[Any], *, field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        abort(400, description=f"{field} must be a string.")
    normalized = value.strip()
    return normalized or None


def _normalize_creation_mode(value: Optional[Any]) -> Optional[str]:
    return _normalize_enum(value, field="creationMode", allowed=_ALLOWED_CREATION_MODES)

def _normalize_optional_float(value: Optional[Any], *, field: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    abort(400, description=f"{field} must be a number.")


def _normalize_float(value: Any, *, field: str) -> float:
    result = _normalize_optional_float(value, field=field)
    if result is None:
        abort(400, description=f"{field} must be a number.")
    return result

def _normalize_measurements(
    section: Optional[Dict[str, Any]], *, section_name: str
) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
    if section is None:
        return {}, {}
    if not isinstance(section, dict):
        abort(400, description=f"{section_name} must be an object of numeric values.")

    normalized: Dict[str, float] = {}
    statuses: Dict[str, Optional[str]] = {}
    for key, value in section.items():
        if not isinstance(key, str):
            abort(400, description=f"Measurement keys in {section_name} must be strings.")
        if key in _MEASUREMENT_STATUS_KEYS:
            if key == "creationMode":
                normalized_status = _normalize_creation_mode(value)
                if normalized_status is not None:
                    statuses[key] = normalized_status
            continue
        if not isinstance(value, (int, float)):
            abort(400, description=f"Measurement '{key}' in {section_name} must be a number.")
        normalized[key] = float(value)
    return normalized, statuses


def _normalize_quick_mode_settings(payload: Optional[Any]) -> Optional[Dict[str, Any]]:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        abort(400, description="quickModeSettings must be an object.")

    allowed_keys = {"bodyShape", "athleticLevel", "measurements"}
    unexpected = [key for key in payload.keys() if key not in allowed_keys]
    if unexpected:
        joined = ", ".join(sorted(unexpected))
        abort(400, description=f"quickModeSettings contains unsupported fields: {joined}.")

    body_shape = payload.get("bodyShape")
    if body_shape is not None and not isinstance(body_shape, str):
        abort(400, description="quickModeSettings.bodyShape must be a string.")
    if isinstance(body_shape, str):
        body_shape = body_shape.strip().lower().replace(" ", "_") or None

    athletic_level = payload.get("athleticLevel")
    if athletic_level is not None and not isinstance(athletic_level, str):
        abort(400, description="quickModeSettings.athleticLevel must be a string.")
    if isinstance(athletic_level, str):
        athletic_level = athletic_level.strip().lower().replace(" ", "_") or None

    measurements_payload = payload.get("measurements")
    measurements: Dict[str, float] = {}
    if measurements_payload is not None:
        if not isinstance(measurements_payload, dict):
            abort(400, description="quickModeSettings.measurements must be an object of numbers.")
        for key, value in measurements_payload.items():
            if not isinstance(key, str):
                abort(400, description="quickModeSettings.measurements keys must be strings.")
            normalized_key = key.strip()
            if not normalized_key:
                abort(
                    400,
                    description="quickModeSettings.measurements keys must not be empty.",
                )
            measurements[normalized_key] = _normalize_float(
                value, field=f"quickModeSettings.measurements['{normalized_key}']"
            )

    normalized: Dict[str, Any] = {}
    if body_shape:
        normalized["bodyShape"] = body_shape
    if athletic_level:
        normalized["athleticLevel"] = athletic_level
    if measurements:
        normalized["measurements"] = measurements

    return normalized or None


def _normalize_morph_entry(morph_id: Any, raw_value: Any) -> Dict[str, Any]:
    if morph_id is None:
        abort(400, description="Morph targets require an 'id'.")
    if not isinstance(morph_id, str):
        morph_id = str(morph_id)
    morph_id = morph_id.strip()
    if not morph_id:
        abort(400, description="Morph target ids must not be empty.")

    backend_key: Optional[str] = None
    slider_value: Optional[float] = None
    unreal_value: Optional[float] = None

    if isinstance(raw_value, dict):
        backend_key_value = raw_value.get("backendKey")
        if backend_key_value is not None:
            if not isinstance(backend_key_value, str):
                backend_key_value = str(backend_key_value)
            backend_key_value = backend_key_value.strip()
            backend_key = backend_key_value or None
        slider_candidate = raw_value.get("sliderValue")
        if slider_candidate is None and "value" in raw_value:
            slider_candidate = raw_value.get("value")
        slider_value = _normalize_optional_float(
            slider_candidate, field=f"morphTargets[{morph_id}].sliderValue"
        )
        unreal_value = _normalize_optional_float(
            raw_value.get("unrealValue"), field=f"morphTargets[{morph_id}].unrealValue"
        )
    elif isinstance(raw_value, (int, float)):
        slider_value = float(raw_value)
    elif raw_value is None:
        slider_value = None
    else:
        abort(
            400,
            description="Morph targets must be numbers or objects containing sliderValue/unrealValue.",
        )

    entry: Dict[str, Any] = {"id": morph_id}
    if backend_key:
        entry["backendKey"] = backend_key
    if slider_value is not None:
        entry["sliderValue"] = slider_value
        entry["value"] = slider_value
    if unreal_value is not None:
        entry["unrealValue"] = unreal_value
    return entry


def _normalize_morph_targets(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    items: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        for morph_id, value in payload.items():
            items.append(_normalize_morph_entry(morph_id, value))
    elif isinstance(payload, IterableABC) and not isinstance(payload, (str, bytes)):
        for entry in payload:
            if isinstance(entry, dict):
                morph_id = entry.get("id")
                if morph_id is None:
                    abort(400, description="Morph targets must include an 'id'.")
                value: Any = entry
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                morph_id, value = entry
            else:
                abort(
                    400,
                    description="Morph targets must be provided as objects with id/value data.",
                )
            items.append(_normalize_morph_entry(morph_id, value))
    else:
        abort(400, description="Morph targets must be provided as an object or list of objects.")
    collapsed: Dict[str, Dict[str, Any]] = {}
    for item in items:
        collapsed[item["id"]] = item

    return [collapsed[key] for key in sorted(collapsed.keys())]


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

    gender = _normalize_enum(payload.get("gender"), field="gender", allowed=_ALLOWED_GENDERS)
    age_range = _normalize_enum(
        payload.get("ageRange"), field="ageRange", allowed=_ALLOWED_AGE_RANGES
    )
    creation_mode = _normalize_creation_mode(payload.get("creationMode"))
    source = _normalize_enum(payload.get("source"), field="source", allowed=_ALLOWED_SOURCES)

    quick_mode_settings = _normalize_quick_mode_settings(payload.get("quickModeSettings"))

    quick_mode_value = payload.get("quickMode")
    if quick_mode_value is None:
        quick_mode = bool(quick_mode_settings)
    elif isinstance(quick_mode_value, bool):
        quick_mode = quick_mode_value or bool(quick_mode_settings)
    else:
        abort(400, description="quickMode must be a boolean value.")

    created_by_session = _normalize_optional_string(
        payload.get("createdBySession"), field="createdBySession"
    )

    basic_measurements, basic_statuses = _normalize_measurements(
        payload.get("basicMeasurements"), section_name="basicMeasurements"
    )
    body_measurements, body_statuses = _normalize_measurements(
        payload.get("bodyMeasurements"), section_name="bodyMeasurements"
    )

    basic_statuses = {k: v for k, v in basic_statuses.items() if v is not None}
    body_statuses = {k: v for k, v in body_statuses.items() if v is not None}

    measurement_creation_mode = basic_statuses.get("creationMode")
    if measurement_creation_mode is None:
        measurement_creation_mode = body_statuses.get("creationMode")

    if measurement_creation_mode is not None:
        if creation_mode is not None and creation_mode != measurement_creation_mode:
            abort(
                400,
                description="creationMode provided in measurements does not match the top-level value.",
            )
        creation_mode = measurement_creation_mode

    morph_targets = _normalize_morph_targets(payload.get("morphTargets"))

    avatar_name = name if isinstance(name, str) else ""

    try:
        if avatar_id is None:
            avatar = repository.create_avatar(
                user_id,
                name=avatar_name,
                gender=gender,
                age_range=age_range,
                creation_mode=creation_mode,
                source=source,
                quick_mode=quick_mode,
                created_by_session=created_by_session,
                basic_measurements=basic_measurements,
                body_measurements=body_measurements,
                morph_targets=morph_targets,
                quick_mode_settings=quick_mode_settings,
                user_context=user_context,
            )
        else:
            avatar = repository.update_avatar(
                user_id,
                avatar_id,
                name=avatar_name,
                gender=gender,
                age_range=age_range,
                creation_mode=creation_mode,
                source=source,
                quick_mode=quick_mode,
                created_by_session=created_by_session,
                basic_measurements=basic_measurements,
                body_measurements=body_measurements,
                morph_targets=morph_targets,
                quick_mode_settings=quick_mode_settings,
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


@avatar_bp.route("/users/<user_id>/avatars/<avatar_id>", methods=["DELETE"])
def delete_avatar(user_id: str, avatar_id: str):
    _require_user_scope(user_id)
    try:
        repository.delete_avatar(user_id, avatar_id)
    except AvatarNotFoundError as exc:
        abort(404, description=str(exc))
    except ValueError:
        abort(400, description="Avatar identifier is invalid.")
    return "", 204