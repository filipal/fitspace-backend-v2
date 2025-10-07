"""Persistence layer for avatar data backed by PostgreSQL."""
from __future__ import annotations

import atexit
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import psycopg2
from psycopg2 import errors
from psycopg2.extras import Json, RealDictCursor, register_uuid
from psycopg2.pool import SimpleConnectionPool


# Measurement keys that should not be treated as numeric values.
_MEASUREMENT_STATUS_KEYS = {"creationMode"}


# ---------------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------------

_pool: Optional[SimpleConnectionPool] = None
_close_registered = False


class RepositoryNotInitialized(RuntimeError):
    """Raised when repository functions are used before initialisation."""


def init_app(app) -> None:
    """Initialise the repository using the Flask application configuration."""

    database_url = app.config.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set app.config['DATABASE_URL'] "
            "or the DATABASE_URL environment variable."
        )

    global _pool, _close_registered
    if _pool is None:
        _pool = SimpleConnectionPool(1, 10, dsn=database_url)

    if not _close_registered:
        atexit.register(close_pool)
        _close_registered = True


def close_pool() -> None:
    """Close the global connection pool (if initialised)."""

    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def _connection() -> Iterator[psycopg2.extensions.connection]:
    if _pool is None:
        raise RepositoryNotInitialized(
            "Avatar repository not initialised. Call avatar.init_app(app) first."
        )

    conn = _pool.getconn()
    try:
        register_uuid(conn_or_curs=conn)
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AvatarError(Exception):
    """Base class for avatar repository errors."""


class AvatarNotFoundError(AvatarError):
    """Raised when the requested avatar cannot be found."""


class DuplicateAvatarNameError(AvatarError):
    """Raised when a user tries to create or rename an avatar with a duplicate name."""


class AvatarQuotaExceededError(AvatarError):
    """Raised when a user exceeds the maximum number of avatars allowed."""


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _ensure_user(conn, user_id: str, *, user_context: Optional[Dict[str, Any]] = None) -> None:
    if not user_context:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (user_id,),
            )
        return

    email = user_context.get("email")
    session_id = user_context.get("session_id")
    issued_at = _coerce_datetime(user_context.get("issued_at"))
    expires_at = _coerce_datetime(user_context.get("expires_at"))
    access_token = user_context.get("access_token")
    refresh_token = user_context.get("refresh_token")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (
                id,
                email,
                session_id,
                issued_at,
                expires_at,
                access_token,
                refresh_token
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET
                email = EXCLUDED.email,
                session_id = EXCLUDED.session_id,
                issued_at = EXCLUDED.issued_at,
                expires_at = EXCLUDED.expires_at,
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                updated_at = NOW()
            """,
            (user_id, email, session_id, issued_at, expires_at, access_token, refresh_token),
        )


def _find_available_slot(conn, user_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT slot FROM avatars WHERE user_id = %s", (user_id,))
        used = {row[0] for row in cur.fetchall()}

    for slot in range(1, 6):
        if slot not in used:
            return slot
    raise AvatarQuotaExceededError("User has reached the maximum of five avatars.")


def _persist_measurements(
    conn,
    avatar_id: uuid.UUID,
    *,
    basic: Dict[str, float],
    body: Dict[str, float],
    morph_targets: Iterable[Dict[str, Any]],
    quick_mode_settings: Optional[Dict[str, Any]],
) -> None:
    basic = {k: v for k, v in basic.items() if k not in _MEASUREMENT_STATUS_KEYS}
    body = {k: v for k, v in body.items() if k not in _MEASUREMENT_STATUS_KEYS}

    with conn.cursor() as cur:
        cur.execute("DELETE FROM avatar_basic_measurements WHERE avatar_id = %s", (avatar_id,))
        cur.execute("DELETE FROM avatar_body_measurements WHERE avatar_id = %s", (avatar_id,))
        cur.execute("DELETE FROM avatar_morph_targets WHERE avatar_id = %s", (avatar_id,))
        cur.execute("DELETE FROM avatar_quickmode_settings WHERE avatar_id = %s", (avatar_id,))

        if basic:
            cur.executemany(
                "INSERT INTO avatar_basic_measurements (avatar_id, measurement_key, value) "
                "VALUES (%s, %s, %s)",
                [(avatar_id, key, value) for key, value in basic.items()],
            )

        if body:
            cur.executemany(
                "INSERT INTO avatar_body_measurements (avatar_id, measurement_key, value) "
                "VALUES (%s, %s, %s)",
                [(avatar_id, key, value) for key, value in body.items()],
            )

        morph_map: Dict[str, Dict[str, Any]] = {}
        for item in morph_targets:
            morph_id = str(item.get("id")) if item.get("id") is not None else ""
            morph_id = morph_id.strip()
            if not morph_id:
                continue
            backend_key = item.get("backendKey")
            if isinstance(backend_key, str):
                backend_key = backend_key.strip() or None
            slider_value = item.get("sliderValue")
            if slider_value is None and "value" in item:
                slider_value = item.get("value")
            if isinstance(slider_value, (int, float)):
                slider_value = float(slider_value)
            else:
                slider_value = None
            unreal_value = item.get("unrealValue")
            if isinstance(unreal_value, (int, float)):
                unreal_value = float(unreal_value)
            else:
                unreal_value = None
            morph_map[morph_id] = {
                "backend_key": backend_key,
                "slider_value": slider_value,
                "unreal_value": unreal_value,
            }

        if morph_map:
            definition_records = [
                (morph_id, data["backend_key"]) for morph_id, data in morph_map.items()
            ]
            cur.executemany(
                """
                INSERT INTO morph_definitions (id, backend_key)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE
                SET
                    backend_key = COALESCE(EXCLUDED.backend_key, morph_definitions.backend_key),
                    updated_at = NOW()
                """,
                definition_records,
            )

            cur.executemany(
                """
                INSERT INTO avatar_morph_targets (
                    avatar_id,
                    morph_id,
                    backend_key,
                    slider_value,
                    unreal_value,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                [
                    (
                        avatar_id,
                        morph_id,
                        data["backend_key"],
                        data["slider_value"],
                        data["unreal_value"],
                    )
                    for morph_id, data in morph_map.items()
                ],
            )

        if quick_mode_settings:
            body_shape = quick_mode_settings.get("bodyShape")
            if isinstance(body_shape, str):
                body_shape = body_shape.strip() or None
            athletic_level = quick_mode_settings.get("athleticLevel")
            if isinstance(athletic_level, str):
                athletic_level = athletic_level.strip() or None
            measurements = quick_mode_settings.get("measurements")
            if not isinstance(measurements, dict):
                measurements = {}
            updated_at_value = quick_mode_settings.get("updatedAt")
            provided_updated_at = _coerce_datetime(updated_at_value)
            timestamp = provided_updated_at or datetime.now(timezone.utc)
            cur.execute(
                """
                INSERT INTO avatar_quickmode_settings (
                    avatar_id,
                    body_shape,
                    athletic_level,
                    measurements,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    avatar_id,
                    body_shape,
                    athletic_level,
                    Json(measurements),
                    timestamp,
                    provided_updated_at or timestamp,
                ),
            )
def _fetch_measurements(
    conn, avatar_id: uuid.UUID
) -> Tuple[
    Dict[str, float],
    Dict[str, float],
    List[Dict[str, Any]],
    Optional[Dict[str, Any]],
]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT measurement_key, value FROM avatar_basic_measurements WHERE avatar_id = %s",
            (avatar_id,),
        )
        basic = {row["measurement_key"]: float(row["value"]) for row in cur.fetchall()}

        cur.execute(
            "SELECT measurement_key, value FROM avatar_body_measurements WHERE avatar_id = %s",
            (avatar_id,),
        )
        body = {row["measurement_key"]: float(row["value"]) for row in cur.fetchall()}

        cur.execute(
            """
            SELECT
                amt.morph_id,
                amt.backend_key,
                amt.slider_value,
                amt.unreal_value,
                amt.updated_at,
                md.backend_key AS definition_backend_key
            FROM avatar_morph_targets AS amt
            LEFT JOIN morph_definitions AS md ON md.id = amt.morph_id
            WHERE amt.avatar_id = %s
            """,
            (avatar_id,),
        )
        morphs: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            slider_value = row.get("slider_value")
            unreal_value = row.get("unreal_value")
            backend_key = row.get("backend_key") or row.get("definition_backend_key")
            updated_at = row.get("updated_at")
            morph_item: Dict[str, Any] = {"id": row["morph_id"]}
            if backend_key:
                morph_item["backendKey"] = backend_key
            if slider_value is not None:
                morph_item["sliderValue"] = float(slider_value)
                morph_item["value"] = float(slider_value)
            if unreal_value is not None:
                morph_item["unrealValue"] = float(unreal_value)
            if isinstance(updated_at, datetime):
                morph_item["updatedAt"] = _isoformat(updated_at)
            morphs.append(morph_item)

        cur.execute(
            """
            SELECT body_shape, athletic_level, measurements, updated_at
            FROM avatar_quickmode_settings
            WHERE avatar_id = %s
            """,
            (avatar_id,),
        )
        quick_row = cur.fetchone()

    quick_mode_settings: Optional[Dict[str, Any]] = None
    if quick_row:
        body_shape = quick_row.get("body_shape")
        athletic_level = quick_row.get("athletic_level")
        measurements_value = quick_row.get("measurements") or {}
        normalized_measurements: Dict[str, Any] = {}
        if isinstance(measurements_value, dict):
            for key, value in measurements_value.items():
                if isinstance(value, (int, float)):
                    normalized_measurements[str(key)] = float(value)
                else:
                    normalized_measurements[str(key)] = value
        updated_at = quick_row.get("updated_at")
        quick_mode_settings = {
            "bodyShape": body_shape,
            "athleticLevel": athletic_level,
            "measurements": normalized_measurements,
        }
        if isinstance(updated_at, datetime):
            quick_mode_settings["updatedAt"] = _isoformat(updated_at)
        if not any(quick_mode_settings.values()):
            quick_mode_settings = None

    morphs.sort(key=lambda item: item["id"])
    return basic, body, morphs, quick_mode_settings


def _row_to_avatar(
    row: Dict[str, object], *, basic, body, morphs, quick_mode_settings
) -> Dict[str, object]:
    created_at = row["created_at"] if isinstance(row["created_at"], datetime) else None
    updated_at = row["updated_at"] if isinstance(row["updated_at"], datetime) else None
    quick_mode_flag = bool(row.get("quick_mode")) if row.get("quick_mode") is not None else False
    if quick_mode_settings:
        quick_mode_flag = quick_mode_flag or True
    return {
        "id": str(row["id"]),
        "userId": row["user_id"],
        "name": row["name"],
        "gender": row.get("gender"),
        "ageRange": row.get("age_range"),
        "creationMode": row.get("creation_mode"),
        "source": row.get("source"),
        "quickMode": quick_mode_flag,
        "createdBySession": row.get("created_by_session"),
        "basicMeasurements": basic,
        "bodyMeasurements": body,
        "morphTargets": morphs,
        "quickModeSettings": quick_mode_settings,
        "createdAt": _isoformat(created_at) if created_at else None,
        "updatedAt": _isoformat(updated_at) if updated_at else None,
    }


# ---------------------------------------------------------------------------
# Repository API
# ---------------------------------------------------------------------------


def list_avatars(
    user_id: str,
    *,
    limit: int = 5,
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, object]:
    with _connection() as conn:
        _ensure_user(conn, user_id, user_context=user_context)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    user_id,
                    name,
                    gender,
                    age_range,
                    creation_mode,
                    source,
                    quick_mode,
                    created_by_session,
                    created_at,
                    updated_at
                FROM avatars
                WHERE user_id = %s
                ORDER BY created_at, id
                """,
                (user_id,),
            )
            rows = cur.fetchall()

        items: List[Dict[str, object]] = []
        for row in rows[:limit]:
            basic, body, morphs, quick_mode_settings = _fetch_measurements(conn, row["id"])
            items.append(
                _row_to_avatar(
                    row,
                    basic=basic,
                    body=body,
                    morphs=morphs,
                    quick_mode_settings=quick_mode_settings,
                )
            )

        return {
            "userId": user_id,
            "limit": limit,
            "count": len(items),
            "total": len(rows),
            "items": items,
        }


def get_avatar(user_id: str, avatar_id: str) -> Dict[str, object]:
    avatar_uuid = uuid.UUID(avatar_id)

    with _connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    user_id,
                    name,
                    gender,
                    age_range,
                    creation_mode,
                    source,
                    quick_mode,
                    created_by_session,
                    created_at,
                    updated_at
                FROM avatars
                WHERE id = %s AND user_id = %s
                """,
                (avatar_uuid, user_id),
            )
            row = cur.fetchone()

        if row is None:
            raise AvatarNotFoundError("Avatar not found.")

        basic, body, morphs, quick_mode_settings = _fetch_measurements(conn, avatar_uuid)
        return _row_to_avatar(
            row,
            basic=basic,
            body=body,
            morphs=morphs,
            quick_mode_settings=quick_mode_settings,
        )


def create_avatar(
    user_id: str,
    *,
    name: str,
    gender: Optional[str],
    age_range: Optional[str],
    creation_mode: Optional[str],
    source: Optional[str],
    quick_mode: bool,
    created_by_session: Optional[str],
    basic_measurements: Dict[str, float],
    body_measurements: Dict[str, float],
    morph_targets: List[Dict[str, Any]],
    quick_mode_settings: Optional[Dict[str, Any]],
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, object]:
    avatar_uuid = uuid.uuid4()

    with _connection() as conn:
        _ensure_user(conn, user_id, user_context=user_context)
        slot = _find_available_slot(conn, user_id)
        avatar_name = name.strip() if name.strip() else "Untitled Avatar"

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO avatars (
                        id,
                        user_id,
                        name,
                        slot,
                        gender,
                        age_range,
                        creation_mode,
                        source,
                        quick_mode,
                        created_by_session
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING
                        id,
                        user_id,
                        name,
                        gender,
                        age_range,
                        creation_mode,
                        source,
                        quick_mode,
                        created_by_session,
                        created_at,
                        updated_at
                    """,
                    (
                        avatar_uuid,
                        user_id,
                        avatar_name,
                        slot,
                        gender,
                        age_range,
                        creation_mode,
                        source,
                        quick_mode,
                        created_by_session,
                    ),
                )
                row = cur.fetchone()
        except errors.UniqueViolation as exc:
            if exc.diag and exc.diag.constraint_name == "avatars_user_id_name_key":
                raise DuplicateAvatarNameError(
                    "Avatar name must be unique per user."
                ) from exc
            raise

        _persist_measurements(
            conn,
            avatar_uuid,
            basic=basic_measurements,
            body=body_measurements,
            morph_targets=morph_targets,
            quick_mode_settings=quick_mode_settings,
        )

        basic, body, morphs, quick_mode_data = _fetch_measurements(conn, avatar_uuid)
        return _row_to_avatar(
            row,
            basic=basic,
            body=body,
            morphs=morphs,
            quick_mode_settings=quick_mode_data,
        )


def update_avatar(
    user_id: str,
    avatar_id: str,
    *,
    name: str,
    gender: Optional[str],
    age_range: Optional[str],
    creation_mode: Optional[str],
    source: Optional[str],
    quick_mode: bool,
    created_by_session: Optional[str],
    basic_measurements: Dict[str, float],
    body_measurements: Dict[str, float],
    morph_targets: List[Dict[str, Any]],
    quick_mode_settings: Optional[Dict[str, Any]],
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, object]:
    avatar_uuid = uuid.UUID(avatar_id)

    with _connection() as conn:
        _ensure_user(conn, user_id, user_context=user_context)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, user_id, name, slot FROM avatars WHERE id = %s AND user_id = %s",
                (avatar_uuid, user_id),
            )
            row = cur.fetchone()

        if row is None:
            raise AvatarNotFoundError("Avatar not found.")

        avatar_name = name.strip() if name.strip() else "Untitled Avatar"

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE avatars
                    SET
                        name = %s,
                        gender = %s,
                        age_range = %s,
                        creation_mode = %s,
                        source = %s,
                        quick_mode = %s,
                        created_by_session = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING
                        id,
                        user_id,
                        name,
                        gender,
                        age_range,
                        creation_mode,
                        source,
                        quick_mode,
                        created_by_session,
                        created_at,
                        updated_at
                    """,
                    (
                        avatar_name,
                        gender,
                        age_range,
                        creation_mode,
                        source,
                        quick_mode,
                        created_by_session,
                        avatar_uuid,
                    ),
                )
                updated = cur.fetchone()
        except errors.UniqueViolation as exc:
            if exc.diag and exc.diag.constraint_name == "avatars_user_id_name_key":
                raise DuplicateAvatarNameError(
                    "Avatar name must be unique per user."
                ) from exc
            raise

        _persist_measurements(
            conn,
            avatar_uuid,
            basic=basic_measurements,
            body=body_measurements,
            morph_targets=morph_targets,
            quick_mode_settings=quick_mode_settings,
        )

        basic, body, morphs, quick_mode_data = _fetch_measurements(conn, avatar_uuid)
        return _row_to_avatar(
            updated,
            basic=basic,
            body=body,
            morphs=morphs,
            quick_mode_settings=quick_mode_data,
        )

def delete_avatar(user_id: str, avatar_id: str) -> None:
    avatar_uuid = uuid.UUID(avatar_id)

    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM avatars WHERE id = %s AND user_id = %s",
                (avatar_uuid, user_id),
            )
            exists = cur.fetchone()

        if not exists:
            raise AvatarNotFoundError("Avatar not found.")

        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM avatar_basic_measurements WHERE avatar_id = %s",
                (avatar_uuid,),
            )
            cur.execute(
                "DELETE FROM avatar_body_measurements WHERE avatar_id = %s",
                (avatar_uuid,),
            )
            cur.execute(
                "DELETE FROM avatar_morph_targets WHERE avatar_id = %s",
                (avatar_uuid,),
            )
            cur.execute(
                "DELETE FROM avatar_quickmode_settings WHERE avatar_id = %s",
                (avatar_uuid,),
            )
            cur.execute(
                "DELETE FROM avatars WHERE id = %s AND user_id = %s",
                (avatar_uuid, user_id),
            )