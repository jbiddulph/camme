"""Shared JWT → User resolution for API routes."""

from fastapi import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User


def current_user_from_auth(authorization: str | None, db: Session, required: bool = False) -> User | None:
    if not authorization or not authorization.lower().startswith('bearer '):
        if required:
            raise HTTPException(status_code=401, detail='Authentication required')
        return None
    token = authorization[7:].strip().strip('"').strip("'")
    if not token:
        if required:
            raise HTTPException(status_code=401, detail='Authentication required')
        return None
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
    except ExpiredSignatureError:
        if required:
            raise HTTPException(
                status_code=401,
                detail='Session expired — please sign in again.',
            )
        return None
    except JWTError:
        if required:
            raise HTTPException(
                status_code=401,
                detail=(
                    'Invalid session token — sign in again. '
                    'If you just deployed the API, SECRET_KEY must stay the same for existing logins, '
                    'or everyone must re-register / log in again.'
                ),
            )
        return None
    subject = claims.get('sub')
    if not isinstance(subject, str) or not subject:
        if required:
            raise HTTPException(status_code=401, detail='Invalid token subject')
        return None
    user = db.scalar(select(User).where(User.email == subject))
    if required and not user:
        raise HTTPException(status_code=401, detail='User not found')
    return user
