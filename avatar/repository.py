"""Persistence layer for avatar data backed by PostgreSQL."""
from __future__ import annotations

import atexit
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool


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


def _ensure_user(conn, user_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))


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
    morph_targets: Iterable[Tuple[str, float]],
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM avatar_basic_measurements WHERE avatar_id = %s", (avatar_id,))
        cur.execute("DELETE FROM avatar_body_measurements WHERE avatar_id = %s", (avatar_id,))
        cur.execute("DELETE FROM avatar_morph_targets WHERE avatar_id = %s", (avatar_id,))

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

        morph_items = list(morph_targets)
        if morph_items:
            cur.executemany(
                "INSERT INTO avatar_morph_targets (avatar_id, morph_id, value) "
                "VALUES (%s, %s, %s)",
                [(avatar_id, morph_id, value) for morph_id, value in morph_items],
            )


def _fetch_measurements(conn, avatar_id: uuid.UUID) -> Tuple[Dict[str, float], Dict[str, float], List[Dict[str, float]]]:
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
            "SELECT morph_id, value FROM avatar_morph_targets WHERE avatar_id = %s",
            (avatar_id,),
        )
        morphs = [
            {"id": row["morph_id"], "value": float(row["value"])}
            for row in cur.fetchall()
        ]

    morphs.sort(key=lambda item: item["id"])
    return basic, body, morphs


def _row_to_avatar(row: Dict[str, object], *, basic, body, morphs) -> Dict[str, object]:
    created_at = row["created_at"] if isinstance(row["created_at"], datetime) else None
    updated_at = row["updated_at"] if isinstance(row["updated_at"], datetime) else None
    return {
        "id": str(row["id"]),
        "userId": row["user_id"],
        "name": row["name"],
        "basicMeasurements": basic,
        "bodyMeasurements": body,
        "morphTargets": morphs,
        "createdAt": _isoformat(created_at) if created_at else None,
        "updatedAt": _isoformat(updated_at) if updated_at else None,
    }


# ---------------------------------------------------------------------------
# Repository API
# ---------------------------------------------------------------------------


def list_avatars(user_id: str, *, limit: int = 5) -> Dict[str, object]:
    with _connection() as conn:
        _ensure_user(conn, user_id)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, user_id, name, created_at, updated_at "
                "FROM avatars WHERE user_id = %s ORDER BY created_at, id",
                (user_id,),
            )
            rows = cur.fetchall()

        items: List[Dict[str, object]] = []
        for row in rows[:limit]:
            basic, body, morphs = _fetch_measurements(conn, row["id"])
            items.append(_row_to_avatar(row, basic=basic, body=body, morphs=morphs))

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
                "SELECT id, user_id, name, created_at, updated_at FROM avatars "
                "WHERE id = %s AND user_id = %s",
                (avatar_uuid, user_id),
            )
            row = cur.fetchone()

        if row is None:
            raise AvatarNotFoundError("Avatar not found.")

        basic, body, morphs = _fetch_measurements(conn, avatar_uuid)
        return _row_to_avatar(row, basic=basic, body=body, morphs=morphs)


def create_avatar(
    user_id: str,
    *,
    name: str,
    basic_measurements: Dict[str, float],
    body_measurements: Dict[str, float],
    morph_targets: List[Dict[str, float]],
) -> Dict[str, object]:
    avatar_uuid = uuid.uuid4()

    with _connection() as conn:
        _ensure_user(conn, user_id)
        slot = _find_available_slot(conn, user_id)
        avatar_name = name.strip() if name.strip() else "Untitled Avatar"

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO avatars (id, user_id, name, slot) "
                    "VALUES (%s, %s, %s, %s) RETURNING id, user_id, name, created_at, updated_at",
                    (avatar_uuid, user_id, avatar_name, slot),
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
            morph_targets=[(item["id"], item["value"]) for item in morph_targets],
        )

        basic, body, morphs = _fetch_measurements(conn, avatar_uuid)
        return _row_to_avatar(row, basic=basic, body=body, morphs=morphs)


def update_avatar(
    user_id: str,
    avatar_id: str,
    *,
    name: str,
    basic_measurements: Dict[str, float],
    body_measurements: Dict[str, float],
    morph_targets: List[Dict[str, float]],
) -> Dict[str, object]:
    avatar_uuid = uuid.UUID(avatar_id)

    with _connection() as conn:
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
                    "UPDATE avatars SET name = %s, updated_at = NOW() "
                    "WHERE id = %s RETURNING id, user_id, name, created_at, updated_at",
                    (avatar_name, avatar_uuid),
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
            morph_targets=[(item["id"], item["value"]) for item in morph_targets],
        )

        basic, body, morphs = _fetch_measurements(conn, avatar_uuid)
        return _row_to_avatar(updated, basic=basic, body=body, morphs=morphs)