-- Token purchases (Stripe Checkout idempotency). Run on existing DBs if not using SQLAlchemy create_all.

CREATE TABLE IF NOT EXISTS camme_token_purchases (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES camme_users(id),
  stripe_checkout_session_id VARCHAR(255) NOT NULL UNIQUE,
  tokens_granted INTEGER NOT NULL,
  amount_total INTEGER NULL,
  currency VARCHAR(8) NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_camme_token_purchases_user_id ON camme_token_purchases(user_id);
