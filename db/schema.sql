-- Database schema for FitSpace avatar persistence.

-- =========================
-- Users
-- =========================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    session_id TEXT,
    issued_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    access_token TEXT,
    refresh_token TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Case-insensitive jedinstvo emaila (ako postoji)
CREATE UNIQUE INDEX IF NOT EXISTS users_email_key
    ON users (lower(email))
    WHERE email IS NOT NULL;

-- Jedinstvo session_id (ako postoji)
CREATE UNIQUE INDEX IF NOT EXISTS users_session_id_key
    ON users (session_id)
    WHERE session_id IS NOT NULL;

-- =========================
-- Avatars
-- =========================
CREATE TABLE IF NOT EXISTS avatars (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slot INTEGER NOT NULL,
    gender TEXT,
    age_range TEXT,
    creation_mode TEXT,
    source TEXT,
    quick_mode BOOLEAN NOT NULL DEFAULT FALSE,
    created_by_session TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT avatars_slot_range CHECK (slot BETWEEN 1 AND 5),
    CONSTRAINT avatars_creation_mode_check CHECK (
        creation_mode IS NULL OR creation_mode IN ('manual', 'scan', 'preset', 'import')
    ),
    CONSTRAINT avatars_user_id_slot_key UNIQUE (user_id, slot)
);

-- Jedinstveno ime avatara po useru (case-insensitive)
CREATE UNIQUE INDEX IF NOT EXISTS avatars_user_id_name_key
    ON avatars (user_id, lower(name));

-- =========================
-- Measurements
-- =========================
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

-- =========================
-- Morph targets
-- =========================
CREATE TABLE IF NOT EXISTS morph_definitions (
    id TEXT PRIMARY KEY,
    backend_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS avatar_morph_targets (
    avatar_id UUID NOT NULL REFERENCES avatars(id) ON DELETE CASCADE,
    morph_id TEXT NOT NULL REFERENCES morph_definitions(id) ON DELETE CASCADE,
    backend_key TEXT,
    slider_value DOUBLE PRECISION,
    unreal_value DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (avatar_id, morph_id)
);

-- =========================
-- QuickMode settings
-- =========================
CREATE TABLE IF NOT EXISTS avatar_quickmode_settings (
    avatar_id UUID PRIMARY KEY REFERENCES avatars(id) ON DELETE CASCADE,
    body_shape TEXT,
    athletic_level TEXT,
    measurements JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================
-- Indeksi
-- =========================
CREATE INDEX IF NOT EXISTS avatar_basic_measurements_avatar_id_idx
    ON avatar_basic_measurements (avatar_id);

CREATE INDEX IF NOT EXISTS avatar_body_measurements_avatar_id_idx
    ON avatar_body_measurements (avatar_id);

CREATE INDEX IF NOT EXISTS avatar_morph_targets_avatar_id_idx
    ON avatar_morph_targets (avatar_id);

-- (za često filtriraš po backend_key)
CREATE INDEX IF NOT EXISTS avatar_morph_targets_backend_key_idx
    ON avatar_morph_targets (backend_key);

-- =========================
-- Check constraints (idempotentno)
-- =========================
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'avatar_quickmode_settings_measurements_is_object'
  ) THEN
    ALTER TABLE avatar_quickmode_settings
      ADD CONSTRAINT avatar_quickmode_settings_measurements_is_object
      CHECK (measurements IS NULL OR jsonb_typeof(measurements) = 'object');
  END IF;
END$$;
