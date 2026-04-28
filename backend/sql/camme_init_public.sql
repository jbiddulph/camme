-- Run on live Postgres / Supabase: SQL Editor → New query → paste → Run.
-- Camme uses the public schema; table names use prefix camme_.
-- Safe to re-run: IF NOT EXISTS on tables and indexes.

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

CREATE TABLE IF NOT EXISTS camme_broadcast_presence (
    id SERIAL PRIMARY KEY,
    room_name VARCHAR(80) NOT NULL,
    user_id INTEGER NOT NULL REFERENCES camme_users (id),
    display_name VARCHAR(80) NOT NULL,
    thumbnail_data_url TEXT,
    is_live BOOLEAN NOT NULL DEFAULT TRUE,
    last_heartbeat_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_camme_broadcast_presence_room_name UNIQUE (room_name),
    CONSTRAINT uq_camme_broadcast_presence_user_id UNIQUE (user_id)
);
