import uuid
from datetime import datetime, timedelta, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from jose import JWTError, jwt
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    AuthResponse,
    ChatMessageCreateRequest,
    ChatMessageItem,
    CreateRoomRequest,
    CreateRoomResponse,
    BroadcastHeartbeatRequest,
    BroadcastLiveItem,
    BroadcastStartResponse,
    LoginRequest,
    LovenseAuthTokenResponse,
    LovenseClientConfigResponse,
    LovenseViewerTargetRequest,
    LovenseViewerTargetResponse,
    RegisterRequest,
    ReportRequest,
    TipCreateRequest,
    TipInboxResponse,
    TipItem,
    UserMeResponse,
    ViewerTokenResponse,
)
from app.core.config import settings
from app.core.livekit_urls import http_to_ws_url
from app.core.security import (
    create_access_token,
    create_private_share_token,
    decode_private_share_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.room import Room
from app.models.user import User
from app.models.broadcast_presence import BroadcastPresence
from app.models.chat_message import ChatMessage
from app.models.tip import Tip
from app.services.livekit_service import issue_room_token
from app.services.lovense_api import (
    encrypt_viewer_control_target,
    fetch_lovense_auth_token,
    lovense_configured,
    platform_configured,
)
from app.services.report_service import persist_report

router = APIRouter()
STREAM_META: dict[str, dict] = {}


def _tip_to_vibration(amount: int) -> tuple[int, int]:
    strength = min(20, max(1, amount // 50))
    seconds = min(120, max(2, amount // 25))
    return strength, seconds


def _broadcaster_user_for_room(room_name: str, db: Session) -> User:
    room = db.scalar(select(Room).where(Room.name == room_name.strip()))
    if not room or not room.created_by_id:
        raise HTTPException(status_code=404, detail='Room or broadcaster not found')
    host = db.scalar(select(User).where(User.id == room.created_by_id))
    if not host:
        raise HTTPException(status_code=404, detail='Broadcaster not found')
    return host


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
        token_balance=1000,
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


@router.get('/users/me', response_model=UserMeResponse)
def read_me(
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> UserMeResponse:
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None
    return UserMeResponse(
        id=user.id,
        username=user.username,
        email=user.email,  # type: ignore[arg-type]
        token_balance=int(user.token_balance),
    )


@router.get('/lovense/client-config', response_model=LovenseClientConfigResponse)
def lovense_client_config() -> LovenseClientConfigResponse:
    return LovenseClientConfigResponse(
        platform=settings.lovense_platform.strip(),
        sdk_enabled=lovense_configured() and platform_configured(),
    )


@router.post('/lovense/auth-token', response_model=LovenseAuthTokenResponse)
def lovense_auth_token(
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> LovenseAuthTokenResponse:
    if not lovense_configured() or not platform_configured():
        raise HTTPException(status_code=503, detail='Lovense is not configured (LOVENSE_TOKEN / LOVENSE_PLATFORM)')
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None
    uid = str(user.id)
    try:
        auth_token = fetch_lovense_auth_token(uid=uid, uname=user.username)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return LovenseAuthTokenResponse(
        auth_token=auth_token,
        platform=settings.lovense_platform.strip(),
        uid=uid,
    )


@router.post('/lovense/viewer-control-target', response_model=LovenseViewerTargetResponse)
def lovense_viewer_control_target(
    payload: LovenseViewerTargetRequest,
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> LovenseViewerTargetResponse:
    _current_user_from_auth(authorization, db, required=True)
    try:
        target = encrypt_viewer_control_target(payload.model_uid.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LovenseViewerTargetResponse(target=target)


@router.post('/tips', response_model=TipItem)
def create_tip(
    payload: TipCreateRequest,
    authorization: str | None = Header(default=None, alias='Authorization'),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
    db: Session = Depends(get_db),
) -> TipItem:
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None
    host = _broadcaster_user_for_room(payload.room_name, db)
    if host.id == user.id:
        raise HTTPException(status_code=400, detail='Cannot tip yourself')

    idem = (payload.idempotency_key or idempotency_key or '').strip() or None
    if idem:
        existing = db.scalar(
            select(Tip).where(Tip.from_user_id == user.id, Tip.idempotency_key == idem)
        )
        if existing:
            from_u = db.scalar(select(User).where(User.id == existing.from_user_id))
            assert from_u is not None
            return TipItem(
                id=existing.id,
                room_name=existing.room_name,
                from_user_id=existing.from_user_id,
                from_display_name=from_u.username,
                to_user_id=existing.to_user_id,
                amount=existing.amount,
                vibrate_strength=existing.vibrate_strength,
                vibrate_seconds=existing.vibrate_seconds,
                created_at_iso=existing.created_at.isoformat(),
            )

    v_strength, v_seconds = _tip_to_vibration(payload.amount)
    from_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if not from_user:
        raise HTTPException(status_code=401, detail='User not found')
    if int(from_user.token_balance) < payload.amount:
        raise HTTPException(status_code=400, detail='Insufficient token balance')

    from_user.token_balance = int(from_user.token_balance) - payload.amount
    tip = Tip(
        from_user_id=user.id,
        to_user_id=host.id,
        room_name=payload.room_name.strip(),
        amount=payload.amount,
        vibrate_strength=v_strength,
        vibrate_seconds=v_seconds,
        idempotency_key=idem,
    )
    db.add(tip)
    db.commit()
    db.refresh(tip)
    return TipItem(
        id=tip.id,
        room_name=tip.room_name,
        from_user_id=tip.from_user_id,
        from_display_name=from_user.username,
        to_user_id=tip.to_user_id,
        amount=tip.amount,
        vibrate_strength=tip.vibrate_strength,
        vibrate_seconds=tip.vibrate_seconds,
        created_at_iso=tip.created_at.isoformat(),
    )


@router.get('/tips/inbox', response_model=TipInboxResponse)
def tips_inbox(
    since_id: int = Query(default=0, ge=0),
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> TipInboxResponse:
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None
    rows = db.scalars(
        select(Tip)
        .where(Tip.to_user_id == user.id, Tip.id > since_id)
        .order_by(Tip.id.asc())
        .limit(100)
    ).all()
    items: list[TipItem] = []
    max_id = since_id
    for tip in rows:
        from_u = db.scalar(select(User).where(User.id == tip.from_user_id))
        name = from_u.username if from_u else '?'
        items.append(
            TipItem(
                id=tip.id,
                room_name=tip.room_name,
                from_user_id=tip.from_user_id,
                from_display_name=name,
                to_user_id=tip.to_user_id,
                amount=tip.amount,
                vibrate_strength=tip.vibrate_strength,
                vibrate_seconds=tip.vibrate_seconds,
                created_at_iso=tip.created_at.isoformat(),
            )
        )
        max_id = max(max_id, tip.id)
    return TipInboxResponse(items=items, max_id=max_id)


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
    visibility: str = Query(default='public'),
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
    selected_visibility = 'private' if visibility.strip().lower() == 'private' else 'public'
    private_share_url: str | None = None
    if selected_visibility == 'private':
        private_share_url = f'/watch/private?share={create_private_share_token(room.name)}'

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
    STREAM_META[room.name] = {
        'visibility': selected_visibility,
        'viewer_count': STREAM_META.get(room.name, {}).get('viewer_count', 0),
        'private_share_url': private_share_url,
    }

    return BroadcastStartResponse(
        room_name=room.name,
        display_name=user.username,
        host_token=host_token,
        viewer_token=viewer_token,
        livekit_url=settings.livekit_url,
        livekit_ws_url=ws_url,
        visibility=selected_visibility,
        private_share_url=private_share_url,
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
    meta = STREAM_META.get(payload.room_name, {})
    if payload.viewer_count is not None:
        meta['viewer_count'] = payload.viewer_count
    if 'visibility' not in meta:
        meta['visibility'] = 'public'
    STREAM_META[payload.room_name] = meta
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
    meta = STREAM_META.get(room)
    if meta:
        meta['viewer_count'] = 0
        STREAM_META[room] = meta
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
            viewer_count=int(STREAM_META.get(row.room_name, {}).get('viewer_count', 0)),
        ).model_dump()
        for row in rows
        if STREAM_META.get(row.room_name, {}).get('visibility', 'public') == 'public'
    ]
    return {'items': items}


@router.post('/broadcast/private-viewer-token', response_model=ViewerTokenResponse)
def private_viewer_token(
    share: str = Query(..., min_length=20),
    db: Session = Depends(get_db),
) -> ViewerTokenResponse:
    room = decode_private_share_token(share)
    if not room:
        raise HTTPException(status_code=401, detail='Invalid or expired private link')
    return _mint_viewer_token(room, db)


@router.post('/reports')
def submit_report(payload: ReportRequest, db: Session = Depends(get_db)) -> dict:
    persist_report(
        db,
        room_name=payload.room_name,
        reported_user=payload.reported_user,
        reason=payload.reason,
    )
    return {'status': 'queued'}


@router.get('/chat/messages')
def list_chat_messages(
    room: str = Query(..., min_length=3, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.room_name == room)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()
    items = [
        ChatMessageItem(
            id=row.id,
            room_name=row.room_name,
            user_id=row.user_id,
            display_name=row.display_name,
            body=row.body,
            created_at_iso=row.created_at.isoformat(),
        ).model_dump()
        for row in reversed(rows)
    ]
    return {'items': items}


@router.post('/chat/messages', response_model=ChatMessageItem)
def create_chat_message(
    payload: ChatMessageCreateRequest,
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> ChatMessageItem:
    room = db.scalar(select(Room).where(Room.name == payload.room_name))
    if not room:
        raise HTTPException(status_code=404, detail='Room not found')
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail='Message cannot be empty')

    user = _current_user_from_auth(authorization, db, required=False)
    if user:
        row = ChatMessage(
            room_name=payload.room_name,
            user_id=user.id,
            display_name=user.username,
            body=body,
        )
    else:
        label = (payload.viewer_display_name or '').strip()
        if len(label) < 2:
            raise HTTPException(status_code=401, detail='Sign in or send viewer_display_name for guest chat')
        row = ChatMessage(
            room_name=payload.room_name,
            user_id=None,
            display_name=label[:80],
            body=body,
        )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ChatMessageItem(
        id=row.id,
        room_name=row.room_name,
        user_id=row.user_id,
        display_name=row.display_name,
        body=row.body,
        created_at_iso=row.created_at.isoformat(),
    )


@router.post('/chat/messages/delete-all')
def delete_all_chat_messages(
    room: str = Query(..., min_length=3, max_length=80),
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> dict:
    user = _current_user_from_auth(authorization, db, required=True)
    assert user is not None
    room_row = db.scalar(select(Room).where(Room.name == room))
    if not room_row or room_row.created_by_id != user.id:
        raise HTTPException(status_code=403, detail='Only the broadcaster can delete this room chat')
    deleted = db.execute(delete(ChatMessage).where(ChatMessage.room_name == room)).rowcount or 0
    db.commit()
    return {'status': 'ok', 'deleted': int(deleted)}
