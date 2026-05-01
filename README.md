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
- Tippers: signed-in viewers use **`POST /api/v1/tips`** (see `/live` tip panel). Broadcasters poll **`GET /api/v1/tips/inbox`**; the page loads the [Standard JS SDK](https://developer.lovense.com/docs/standard-solutions/standard-js-sdk.html) and calls `sendToyCommand` when new tips arrive.

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

- User registration/login (starter token flow) persisted in PostgreSQL (`camme_users`)
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
