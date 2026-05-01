import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.payment_routes import router as payment_router
from app.api.routes import router as api_router
from app.core.config import settings
from app.db.session import init_db

log = logging.getLogger('uvicorn.error')


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_db()
        log.info('Database tables ensured (create_all).')
    except Exception:
        log.exception('init_db failed — check POSTGRES_DSN and SSL settings')
        raise
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(',')],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(payment_router, prefix=settings.api_prefix)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(_request, exc: SQLAlchemyError):
    log.exception('SQLAlchemy error')
    detail = (
        'Database error. For Supabase cloud, use POSTGRES_SSLMODE=require '
        'or add ?sslmode=require to POSTGRES_DSN. Use Session mode / port 5432 if the pooler rejects DDL.'
    )
    if settings.debug:
        detail = str(exc)
    return JSONResponse(status_code=500, content={'detail': detail})


@app.get('/')
def root() -> dict:
    return {'name': settings.app_name, 'docs': '/docs'}
