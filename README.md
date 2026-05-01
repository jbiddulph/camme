# Camme

Camme is a starter social cam + chat web app architecture using:

- **Backend brain:** Python + FastAPI
- **Web app frontend:** Go (SSR templates + minimal JS)
- **Video infrastructure:** LiveKit (Go-based SFU)
- **Database:** PostgreSQL (or Supabase Postgres)
- **Realtime events + queues:** Redis
- **Payments:** Stripe (web) and Apple IAP (mobile)

> This repository is a production-minded foundation, not a full platform yet.

## Project Layout

- `backend/` - FastAPI service for auth, profiles, chat events, rooms/tokens, moderation/reporting
- `frontend-go/` - Go web application server and templates
- `infra/` - Local development infrastructure (Postgres, Redis, LiveKit)

## Lovense (tips → toy vibration)

- Set **`LOVENSE_TOKEN`** (developer token) and **`LOVENSE_PLATFORM`** (Website Name from the Lovense developer dashboard) on the API. Optional: **`LOVENSE_AES_KEY`** / **`LOVENSE_AES_IV`** for [Viewer JS `startControl`](https://developer.lovense.com/docs/cam-solutions/viewer-js) (`POST /api/v1/lovense/viewer-control-target`).
- New users get **1000** `token_balance` (column on `camme_users`). Run **`backend/sql/migration_lovense_tokens.sql`** on existing databases.
- Tippers: signed-in viewers use **`POST /api/v1/tips`** (see `/live` tip panel). Broadcasters poll **`GET /api/v1/tips/inbox`** for realtime Lovense cues; **`GET /api/v1/tips/earnings`** (and the web page **`/tips`**) list who tipped, how many tokens, and totals toward payout. Visiting **`/tips/inbox`** in the browser redirects to **`/tips`** (the JSON inbox remains at **`/api/v1/tips/inbox`**).
- Economics env vars: **`INITIAL_TOKEN_BALANCE`** (default 1000 for dev/test; set **`0`** when tokens are purchase-only), **`TOKEN_VALUE_GBP`** (default 0.05 per tip token to the model), **`PAYOUT_MINIMUM_GBP`** (default 50.00).

**How Camme links a broadcaster to Lovense (not your Lovense app “username”):** the API calls Lovense `getToken` with **`uid = str(camme_user.id)`** and **`uname = camme_username`** (see `POST /api/v1/lovense/auth-token`). Lovense ties the browser SDK session to that **`uid`** under **your** developer token + **platform** (website name). The toy is controlled when **Lovense Connect** is running and associated with that same integration; you do **not** need the Camme username to match a Lovense nickname. Tips are delivered in-app via your API (`tips/inbox`); `sendToyCommand` runs in the broadcaster’s browser on that SDK session.

## Stripe — buying tokens (`/buy-tokens`)

- **Web page:** **`/buy-tokens`** (Go app). **API:** `GET /api/v1/payments/stripe/packages`, `POST /api/v1/payments/stripe/checkout` (Bearer JWT), `POST /api/v1/payments/stripe/webhook` (Stripe-signed, no JWT).
- **Env (API / Heroku `camme-api`):** **`STRIPE_SECRET_KEY`**, **`STRIPE_WEBHOOK_SECRET`**, **`STRIPE_PUBLISHABLE_KEY`** (safe to expose; returned on `/packages` for future client use), **`STRIPE_FRONTEND_BASE_URL`** (e.g. `https://www.exhibitionist.me` — used for Checkout success/cancel URLs), **`SITE_DISPLAY_NAME`** (product copy). Optional **`STRIPE_PACKAGES_JSON`** overrides default packs in `app/services/stripe_checkout.py`.
- **Webhook URL in Stripe Dashboard:** `https://<your-api-host>/api/v1/payments/stripe/webhook` (same path if the API is only reachable under a prefix — adjust to match production). After payment, **`checkout.session.completed`** credits **`token_balance`** idempotently (`camme_token_purchases`).

### How Exhibitionist.me / the platform earns money

1. **Markup on token packs (implemented):** You set real-money prices in Stripe; each pack grants a fixed number of tipping tokens. Viewers pay **you** via Stripe. When they tip, models accrue earnings at **`TOKEN_VALUE_GBP`** per token (e.g. £0.05). If a pack sells **100 tokens for £5.99** and each tipped token is worth **£0.05** to the model, you keep roughly the gap after Stripe fees — e.g. full £5.99 if none tipped yet, or the difference between price paid and model liability as tokens move. Tune **`STRIPE_PACKAGES_JSON`** / defaults so average **price per token is above `TOKEN_VALUE_GBP`** plus your costs.
2. **Fee on payouts (Stripe Connect — not implemented here):** Pay models through **Connect** and take **`application_fee_percent`** or a fixed fee on each transfer; your platform account receives that fee automatically.
3. **Take rate on tips (policy change):** You could credit models at less than one **`TOKEN_VALUE_GBP`** per token (or deduct a platform % before recording earnings). That would require product/accounting changes beyond the current “1 tipped token = `TOKEN_VALUE_GBP` to model” rule.

**Starter tokens:** **`INITIAL_TOKEN_BALANCE`** (e.g. `0` in production if all spend is purchased).

## Quick Start

### 1) Start infra

```bash
cd infra
docker compose up -d
```

### 2) Start backend

```bash
cd ../backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 3) Start frontend (Go)

```bash
cd ../frontend-go
cp .env.example .env
go mod tidy
go run .
```

Frontend runs on `http://localhost:8080` and proxies API calls to backend (`http://localhost:8000`).

## Core Flows Included

- User registration/login (optional starter tokens via **`INITIAL_TOKEN_BALANCE`**) persisted in PostgreSQL (`camme_users`)
- **Stripe Checkout** token packs (`/buy-tokens`, webhook credit to `token_balance`)
- Room creation/listing persisted in PostgreSQL (`camme_rooms`)
- LiveKit access token generation (host/viewer) + **WebSocket URL** for browser clients
- **Broadcast / watch** pages at `/live` (camera + mic for hosts; subscribe-only for viewers)
- Moderation reports stored in PostgreSQL (`camme_reports`)
- Health endpoints for infrastructure checks

## Next Production Steps

1. Add Alembic migrations (today tables are created on startup via `create_all` for dev)
2. Add robust auth (hashed passwords + JWT refresh + RBAC)
3. Add chat persistence and moderation automations
4. Add Stripe Connect payout flows and subscription lifecycle webhooks
5. Add KYC/age verification and compliance controls
6. Add observability (OpenTelemetry, structured logs, SLOs)

## Video troubleshooting (local dev)

1. **Prove the browser can use the camera:** open **`http://localhost:8080/cam-test`**, click **Start camera**. You should see yourself and the camera LED. If not, fix macOS **Privacy → Camera/Microphone** for your browser and use a normal Chrome/Safari window (not an IDE embedded browser).
2. **Restart LiveKit after config changes:** `cd infra && docker compose up -d livekit --force-recreate`  
   Local `livekit.yaml` sets **`rtc.node_ip: 127.0.0.1`** and **`use_external_ip: false`** so WebRTC from the host hits Docker-mapped UDP ports instead of a bad advertised IP.
3. Then use **Broadcast** on `/live`: Step 1 (browser test), then Step 2 after **Connected**.

## Notes

- If you use Supabase, point backend DB settings to Supabase Postgres and use Supabase Auth/JWT verification where needed.
- LiveKit server is external in production; this local stack is for development only.
- Database naming rule: all tables must be prefixed with `camme_` (for example, `camme_users`, `camme_rooms`, `camme_messages`).
