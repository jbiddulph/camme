import uuid
from datetime import datetime, timedelta, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    AuthResponse,
    CreateRoomRequest,
    CreateRoomResponse,
    BroadcastHeartbeatRequest,
    BroadcastLiveItem,
    BroadcastStartResponse,
    LoginRequest,
    RegisterRequest,
    ReportRequest,
    ViewerTokenResponse,
)
from app.core.config import settings
from app.core.livekit_urls import http_to_ws_url
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.room import Room
from app.models.user import User
from app.models.broadcast_presence import BroadcastPresence
from app.services.livekit_service import issue_room_token
from app.services.report_service import persist_report

router = APIRouter()


def _sanitize_room_suffix(value: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9_-]+', '-', value.strip().lower()).strip('-')
    if not clean:
        clean = uuid.uuid4().hex[:8]
    return clean[:60]


def _current_user_from_auth(authorization: str | None, db: Session, required: bool = False) -> User | None:
    if not authorization or not authorization.lower().startswith('bearer '):
        if required:
            raise HTTPException(status_code=401, detail='Authentication required')
        return None
    token = authorization[7:].strip()
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
    except JWTError:
        if required:
            raise HTTPException(status_code=401, detail='Invalid token')
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


@router.get('/health')
def health() -> dict:
    return {'status': 'ok', 'service': settings.app_name}


@router.post('/auth/register', response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail='Email already registered')

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Email already registered')

    token = create_access_token(subject=payload.email)
    return AuthResponse(access_token=token)


@router.post('/auth/login', response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid credentials')

    token = create_access_token(subject=payload.email)
    return AuthResponse(access_token=token)


@router.get('/rooms')
def list_rooms(db: Session = Depends(get_db)) -> dict:
    names = db.scalars(select(Room.name).order_by(Room.created_at.desc())).all()
    return {'rooms': list(names)}


@router.post('/rooms', response_model=CreateRoomResponse)
def create_room(
    payload: CreateRoomRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias='Authorization'),
) -> CreateRoomResponse:
    existing = db.scalar(select(Room).where(Room.name == payload.room_name))
    if existing:
        raise HTTPException(status_code=409, detail='Room name already exists')

    user = _current_user_from_auth(authorization, db, required=False)
    creator_id = user.id if user else None

    room = Room(name=payload.room_name, created_by_id=creator_id)
    db.add(room)
    db.commit()

    host_token = issue_room_token(identity=f'host:{payload.room_name}', room_name=payload.room_name, can_publish=True)
    viewer_token = issue_room_token(identity=f'viewer:{payload.room_name}', room_name=payload.room_name, can_publish=False)
    ws_url = http_to_ws_url(settings.livekit_url)

    return CreateRoomResponse(
        room_name=payload.room_name,
        host_token=host_token,
        viewer_token=viewer_token,
        livekit_url=settings.livekit_url,
        livekit_ws_url=ws_url,
    )


def _mint_viewer_token(room_name: str, db: Session) -> ViewerTokenResponse:
    existing = db.scalar(select(Room).where(Room.name == room_name))
    if not existing:
        raise HTTPException(
            status_code=404,
            detail='Room not found — create it on the home page first (same exact name), then click Watch live.',
        )

    suffix = uuid.uuid4().hex[:10]
    viewer_token = issue_room_token(
        identity=f'viewer:{room_name}:{suffix}',
        room_name=room_name,
        can_publish=False,
    )
    ws_url = http_to_ws_url(settings.livekit_url)

    return ViewerTokenResponse(
        room_name=room_name,
        viewer_token=viewer_token,
        livekit_url=settings.livekit_url,
        livekit_ws_url=ws_url,
    )


@router.post('/room/viewer-token', response_model=ViewerTokenResponse)
def issue_viewer_token_query(
    room: str = Query(..., min_length=3, max_length=80),
    db: Session = Depends(get_db),
) -> ViewerTokenResponse:
    """Preferred for Watch links: avoids path-encoding issues with special room names."""
    return _mint_viewer_token(room.strip(), db)


@router.post('/rooms/{room_name}/viewer-token', response_model=ViewerTokenResponse)
def issue_viewer_token(room_name: str, db: Session = Depends(get_db)) -> ViewerTokenResponse:
    """Mint a fresh viewer JWT for an existing room so watchers can return anytime."""
    return _mint_viewer_token(room_name, db)


@router.post('/broadcast/start', response_model=BroadcastStartResponse)
def start_broadcast(
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> BroadcastStartResponse:
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None

    room = db.scalar(select(Room).where(Room.created_by_id == user.id).order_by(Room.created_at.asc()))
    if not room:
        room_name = f'live-{_sanitize_room_suffix(user.username or user.email.split("@")[0])}'
        existing_by_name = db.scalar(select(Room).where(Room.name == room_name))
        if existing_by_name and existing_by_name.created_by_id != user.id:
            room_name = f'{room_name}-{uuid.uuid4().hex[:6]}'
        room = Room(name=room_name, created_by_id=user.id)
        db.add(room)
        db.commit()

    host_token = issue_room_token(identity=f'host:{room.name}', room_name=room.name, can_publish=True)
    viewer_token = issue_room_token(identity=f'viewer:{room.name}', room_name=room.name, can_publish=False)
    ws_url = http_to_ws_url(settings.livekit_url)

    presence = db.scalar(select(BroadcastPresence).where(BroadcastPresence.user_id == user.id))
    if not presence:
        presence = BroadcastPresence(
            room_name=room.name,
            user_id=user.id,
            display_name=user.username,
            is_live=True,
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.add(presence)
    else:
        presence.room_name = room.name
        presence.display_name = user.username
        presence.is_live = True
        presence.last_heartbeat_at = datetime.now(timezone.utc)
    db.commit()

    return BroadcastStartResponse(
        room_name=room.name,
        display_name=user.username,
        host_token=host_token,
        viewer_token=viewer_token,
        livekit_url=settings.livekit_url,
        livekit_ws_url=ws_url,
    )


@router.post('/broadcast/heartbeat')
def heartbeat_broadcast(
    payload: BroadcastHeartbeatRequest,
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> dict:
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None
    room = db.scalar(select(Room).where(Room.name == payload.room_name))
    if not room or room.created_by_id != user.id:
        raise HTTPException(status_code=403, detail='Not your room')

    presence = db.scalar(select(BroadcastPresence).where(BroadcastPresence.user_id == user.id))
    if not presence:
        presence = BroadcastPresence(
            room_name=payload.room_name,
            user_id=user.id,
            display_name=user.username,
        )
        db.add(presence)
    presence.room_name = payload.room_name
    presence.display_name = user.username
    presence.is_live = True
    if payload.thumbnail_data_url:
        presence.thumbnail_data_url = payload.thumbnail_data_url
    presence.last_heartbeat_at = datetime.now(timezone.utc)
    db.commit()
    return {'status': 'ok'}


@router.post('/broadcast/stop')
def stop_broadcast(
    room: str = Query(..., min_length=3, max_length=80),
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> dict:
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None
    presence = db.scalar(select(BroadcastPresence).where(BroadcastPresence.user_id == user.id))
    if presence and presence.room_name == room:
        presence.is_live = False
        presence.last_heartbeat_at = datetime.now(timezone.utc)
        db.commit()
    return {'status': 'ok'}


@router.get('/broadcast/live')
def list_live_broadcasts(db: Session = Depends(get_db)) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    rows = db.scalars(
        select(BroadcastPresence)
        .where(BroadcastPresence.is_live.is_(True))
        .where(BroadcastPresence.last_heartbeat_at >= cutoff)
        .order_by(BroadcastPresence.last_heartbeat_at.desc())
    ).all()
    items = [
        BroadcastLiveItem(
            room_name=row.room_name,
            display_name=row.display_name,
            thumbnail_data_url=row.thumbnail_data_url,
            last_heartbeat_iso=row.last_heartbeat_at.isoformat(),
        ).model_dump()
        for row in rows
    ]
    return {'items': items}


@router.post('/reports')
def submit_report(payload: ReportRequest, db: Session = Depends(get_db)) -> dict:
    persist_report(
        db,
        room_name=payload.room_name,
        reported_user=payload.reported_user,
        reason=payload.reason,
    )
    return {'status': 'queued'}
