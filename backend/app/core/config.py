from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Camme API'
    api_prefix: str = '/api/v1'
    secret_key: str = 'change-me'
    access_token_expire_minutes: int = 60

    postgres_dsn: str = 'postgresql+psycopg://camme:camme@localhost:5432/camme'
    # Supabase cloud (and many hosted Postgres) need TLS: set require or add ?sslmode=require to POSTGRES_DSN
    postgres_sslmode: str | None = None
    db_table_prefix: str = 'camme_'
    debug: bool = False
    redis_url: str = 'redis://localhost:6379/0'

    livekit_url: str = 'http://localhost:7880'
    livekit_api_key: str = 'devkey'
    livekit_api_secret: str = 'secret'

    stripe_secret_key: str = 'sk_test_replace_me'
    allowed_origins: str = 'http://localhost:8080'

    # Lovense Standard API — developer dashboard: https://developer.lovense.com
    # LOVENSE_TOKEN = developer token (server-side only). LOVENSE_PLATFORM = Website Name in dashboard.
    # LOVENSE_AES_KEY / LOVENSE_AES_IV = Viewer JS startControl (optional); Standard JS getToken does not use AES.
    lovense_token: str = ''
    lovense_platform: str = ''
    lovense_aes_key: str = ''
    lovense_aes_iv: str = ''


settings = Settings()
