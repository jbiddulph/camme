-- Run in Supabase: SQL Editor → New query → paste → Run.
-- Camme uses the public schema; names are prefixed camme_.
-- If the FastAPI app already started with POSTGRES_DSN pointed at this DB, these may already exist (IF NOT EXISTS is safe).

CREATE TABLE IF NOT EXISTS camme_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(40) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_camme_users_username ON camme_users (username);
CREATE INDEX IF NOT EXISTS ix_camme_users_email ON camme_users (email);

CREATE TABLE IF NOT EXISTS camme_rooms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL UNIQUE,
    created_by_id INTEGER REFERENCES camme_users (id),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_camme_rooms_name ON camme_rooms (name);

CREATE TABLE IF NOT EXISTS camme_reports (
    id SERIAL PRIMARY KEY,
    room_name VARCHAR(80) NOT NULL,
    reported_user VARCHAR(255) NOT NULL,
    reason TEXT NOT NULL,
    status VARCHAR(32) DEFAULT 'queued' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_camme_reports_room_name ON camme_reports (room_name);
