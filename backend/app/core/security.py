from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8'),
    )


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    exp = datetime.now(tz=timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {'sub': subject, 'exp': exp}
    return jwt.encode(payload, settings.secret_key, algorithm='HS256')


def create_private_share_token(room_name: str, expires_minutes: int = 24 * 60) -> str:
    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {'scope': 'private_share', 'room': room_name, 'exp': exp}
    return jwt.encode(payload, settings.secret_key, algorithm='HS256')


def decode_private_share_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
    except Exception:
        return None
    if payload.get('scope') != 'private_share':
        return None
    room = payload.get('room')
    if not isinstance(room, str) or not room:
        return None
    return room
