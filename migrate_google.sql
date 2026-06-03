-- migrate_google.sql — Wasapeame
-- Añade columnas de Google Calendar a la tabla negocios

ALTER TABLE negocios
    ADD COLUMN IF NOT EXISTS google_access_token  TEXT,
    ADD COLUMN IF NOT EXISTS google_refresh_token TEXT,
    ADD COLUMN IF NOT EXISTS google_token_expires  TIMESTAMPTZ;
