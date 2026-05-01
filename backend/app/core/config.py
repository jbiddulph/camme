import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# On Heroku (DYNO set), do not load a bundled .env — Config Vars must win.
_ENV_FILE = '.env' if not os.environ.get('DYNO') else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding='utf-8',
        extra='ignore',
    )

    app_name: str = 'Camme API'
    # Shown in Stripe product text and emails to users
    site_display_name: str = 'Exhibitionist.me'
    api_prefix: str = '/api/v1'
    secret_key: str = 'change-me'
    access_token_expire_minutes: int = 60

    postgres_dsn: str = 'postgresql+psycopg://camme:camme@localhost:5432/camme'
    # Supabase cloud (and many hosted Postgres) need TLS: set require or add ?sslmode=require to POSTGRES_DSN
    postgres_sslmode: str | None = None
    # Token economy. INITIAL_TOKEN_BALANCE=0 when tokens are purchase-only in production.
    initial_token_balance: int = 1000
    token_value_gbp: float = 0.05
    payout_minimum_gbp: float = 50.0
    db_table_prefix: str = 'camme_'
    debug: bool = False
    redis_url: str = 'redis://localhost:6379/0'

    livekit_url: str = 'http://localhost:7880'
    livekit_api_key: str = 'devkey'
    livekit_api_secret: str = 'secret'

    # Stripe — https://dashboard.stripe.com/apikeys  (use test keys in dev)
    stripe_secret_key: str = ''
    stripe_webhook_secret: str = ''
    stripe_publishable_key: str = ''
    # Absolute base URL of the public web app (for Checkout success/cancel redirects)
    stripe_frontend_base_url: str = 'http://localhost:8080'
    # Optional JSON override for token packages: [{"id":"t100","label":"100 tokens","tokens":100,"unit_amount":499,"currency":"gbp"}, ...]
    # unit_amount = minor units (pence for gbp). If empty, built-in defaults are used.
    stripe_packages_json: str = ''
    # Custom “buy N tokens” checkout: total charged = round(tokens * gbp * 100) pence (min ~£0.30 Stripe rule)
    stripe_gbp_per_token_purchase: float = 0.0499
    stripe_minimum_charge_gbp: float = 0.30
    stripe_custom_tokens_max: int = 50_000
    allowed_origins: str = 'http://localhost:8080'

    @field_validator('stripe_secret_key', 'stripe_publishable_key', 'stripe_webhook_secret', mode='before')
    @classmethod
    def _strip_quotes_on_secrets(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        s = v.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
            s = s[1:-1].strip()
        return s

    # Lovense Standard API — developer dashboard: https://developer.lovense.com
    # LOVENSE_TOKEN = developer token (server-side only). LOVENSE_PLATFORM = Website Name in dashboard.
    # LOVENSE_AES_KEY / LOVENSE_AES_IV = Viewer JS startControl (optional); Standard JS getToken does not use AES.
    lovense_token: str = ''
    lovense_platform: str = ''
    lovense_aes_key: str = ''
    lovense_aes_iv: str = ''


settings = Settings()
