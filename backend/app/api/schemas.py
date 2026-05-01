from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class CreateRoomRequest(BaseModel):
    room_name: str = Field(min_length=3, max_length=80)


class CreateRoomResponse(BaseModel):
    room_name: str
    host_token: str
    viewer_token: str
    livekit_url: str
    livekit_ws_url: str


class ViewerTokenResponse(BaseModel):
    room_name: str
    viewer_token: str
    livekit_url: str
    livekit_ws_url: str


class BroadcastStartResponse(BaseModel):
    room_name: str
    display_name: str
    host_token: str
    viewer_token: str
    livekit_url: str
    livekit_ws_url: str
    visibility: str = 'public'
    private_share_url: str | None = None


class BroadcastHeartbeatRequest(BaseModel):
    room_name: str = Field(min_length=3, max_length=80)
    thumbnail_data_url: str | None = Field(default=None, max_length=2_000_000)
    viewer_count: int | None = Field(default=None, ge=0, le=100000)


class BroadcastLiveItem(BaseModel):
    room_name: str
    display_name: str
    thumbnail_data_url: str | None = None
    last_heartbeat_iso: str
    viewer_count: int = 0


class ReportRequest(BaseModel):
    room_name: str
    reported_user: str
    reason: str = Field(min_length=5, max_length=500)


class ChatMessageCreateRequest(BaseModel):
    room_name: str = Field(min_length=3, max_length=80)
    body: str = Field(min_length=1, max_length=2000)
    # When not logged in, viewers send their on-screen label (e.g. Viewer1).
    viewer_display_name: str | None = Field(default=None, max_length=80)


class ChatMessageItem(BaseModel):
    id: int
    room_name: str
    user_id: int | None
    display_name: str
    body: str
    created_at_iso: str


class UserMeResponse(BaseModel):
    id: int
    username: str
    email: str
    token_balance: int


class LovenseClientConfigResponse(BaseModel):
    platform: str
    sdk_enabled: bool


class LovenseAuthTokenResponse(BaseModel):
    auth_token: str
    platform: str
    uid: str


class LovenseViewerTargetRequest(BaseModel):
    model_uid: str = Field(min_length=1, max_length=128)


class LovenseViewerTargetResponse(BaseModel):
    target: str


class TipCreateRequest(BaseModel):
    room_name: str = Field(min_length=3, max_length=80)
    amount: int = Field(ge=1, le=50_000)
    idempotency_key: str | None = Field(default=None, max_length=64)


class TipItem(BaseModel):
    id: int
    room_name: str
    from_user_id: int
    from_display_name: str
    to_user_id: int
    amount: int
    vibrate_strength: int
    vibrate_seconds: int
    created_at_iso: str


class TipInboxResponse(BaseModel):
    items: list[TipItem]
    max_id: int


class TipsEarningsResponse(BaseModel):
    """Totals for tips received by the authenticated user (broadcaster)."""

    token_value_gbp: float
    payout_minimum_gbp: float
    total_tokens_received: int
    total_earned_gbp: float
    until_payout_gbp: float
    payout_eligible: bool
    tips: list[TipItem]
