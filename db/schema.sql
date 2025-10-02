-- Database schema for FitSpace avatar persistence.

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS avatars (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slot INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT avatars_slot_range CHECK (slot BETWEEN 1 AND 5),
    CONSTRAINT avatars_user_id_slot_key UNIQUE (user_id, slot)
);

-- Enforce unique avatar names per user (case-insensitive).
CREATE UNIQUE INDEX IF NOT EXISTS avatars_user_id_name_key
    ON avatars (user_id, lower(name));

CREATE TABLE IF NOT EXISTS avatar_basic_measurements (
    avatar_id UUID NOT NULL REFERENCES avatars(id) ON DELETE CASCADE,
    measurement_key TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (avatar_id, measurement_key)
);

CREATE TABLE IF NOT EXISTS avatar_body_measurements (
    avatar_id UUID NOT NULL REFERENCES avatars(id) ON DELETE CASCADE,
    measurement_key TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (avatar_id, measurement_key)
);

CREATE TABLE IF NOT EXISTS avatar_morph_targets (
    avatar_id UUID NOT NULL REFERENCES avatars(id) ON DELETE CASCADE,
    morph_id TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (avatar_id, morph_id)
);

CREATE INDEX IF NOT EXISTS avatar_basic_measurements_avatar_id_idx
    ON avatar_basic_measurements (avatar_id);
CREATE INDEX IF NOT EXISTS avatar_body_measurements_avatar_id_idx
    ON avatar_body_measurements (avatar_id);
CREATE INDEX IF NOT EXISTS avatar_morph_targets_avatar_id_idx
    ON avatar_morph_targets (avatar_id);