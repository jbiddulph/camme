from livekit import api

from app.core.config import settings


def issue_room_token(identity: str, room_name: str, can_publish: bool = True) -> str:
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=can_publish,
                can_subscribe=True,
            )
        )
    )
    return token.to_jwt()
