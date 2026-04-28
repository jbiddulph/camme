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


class BroadcastHeartbeatRequest(BaseModel):
    room_name: str = Field(min_length=3, max_length=80)
    thumbnail_data_url: str | None = Field(default=None, max_length=2_000_000)


class BroadcastLiveItem(BaseModel):
    room_name: str
    display_name: str
    thumbnail_data_url: str | None = None
    last_heartbeat_iso: str


class ReportRequest(BaseModel):
    room_name: str
    reported_user: str
    reason: str = Field(min_length=5, max_length=500)
