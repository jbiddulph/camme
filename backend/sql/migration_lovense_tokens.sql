-- Camme: Lovense tips + user token balances (run once on existing DBs).
-- Safe to re-run where supported.

ALTER TABLE camme_users
  ADD COLUMN IF NOT EXISTS token_balance INTEGER NOT NULL DEFAULT 1000;

CREATE TABLE IF NOT EXISTS camme_tips (
  id SERIAL PRIMARY KEY,
  from_user_id INTEGER NOT NULL REFERENCES camme_users (id),
  to_user_id INTEGER NOT NULL REFERENCES camme_users (id),
  room_name VARCHAR(80) NOT NULL,
  amount INTEGER NOT NULL CHECK (amount > 0),
  vibrate_strength INTEGER NOT NULL,
  vibrate_seconds INTEGER NOT NULL,
  idempotency_key VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_camme_tips_to_user ON camme_tips (to_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_camme_tips_from_user ON camme_tips (from_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_camme_tips_room ON camme_tips (room_name);
CREATE UNIQUE INDEX IF NOT EXISTS uq_camme_tips_idempotency
  ON camme_tips (from_user_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
