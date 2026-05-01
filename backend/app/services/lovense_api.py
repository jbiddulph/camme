"""Server-side calls to Lovense HTTPS API (getToken) and AES helper for Viewer JS control targets."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from app.core.config import settings

LOVENSE_GET_TOKEN_URL = 'https://api.lovense-api.com/api/basicApi/getToken'


def lovense_configured() -> bool:
    return bool(settings.lovense_token and settings.lovense_token.strip())


def platform_configured() -> bool:
    return bool(settings.lovense_platform and settings.lovense_platform.strip())


def fetch_lovense_auth_token(*, uid: str, uname: str, utoken: str | None = None) -> str:
    """
    Exchange developer token for a per-user authToken (Standard Socket / Standard JS SDK).
    See: https://developer.lovense.com/docs/standard-solutions/socket-api.html
    """
    if not lovense_configured():
        raise RuntimeError('LOVENSE_TOKEN is not configured')

    body: dict[str, Any] = {
        'token': settings.lovense_token.strip(),
        'uid': uid,
        'uname': uname,
    }
    if utoken:
        body['utoken'] = utoken

    with httpx.Client(timeout=20.0) as client:
        resp = client.post(LOVENSE_GET_TOKEN_URL, json=body)
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f'Lovense getToken invalid JSON (HTTP {resp.status_code}): {exc}') from exc

    if resp.status_code >= 400:
        raise RuntimeError(data.get('message') or f'Lovense HTTP {resp.status_code}')
    if data.get('code') != 0:
        raise RuntimeError(str(data.get('message') or 'Lovense getToken failed'))
    inner = data.get('data') or {}
    auth = inner.get('authToken')
    if not isinstance(auth, str) or not auth:
        raise RuntimeError('Lovense getToken missing authToken')
    return auth


def encrypt_viewer_control_target(model_uid: str) -> str:
    """
    AES/CBC/PKCS7 + Base64, matching Lovense Viewer JS docs (Java example).
    Payload before encrypt: {"uid": "<modelUid>", "time": <ms> }
    """
    if not settings.lovense_aes_key or not settings.lovense_aes_iv:
        raise RuntimeError('LOVENSE_AES_KEY and LOVENSE_AES_IV are not configured')

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    payload = json.dumps({'uid': model_uid, 'time': int(time.time() * 1000)}, separators=(',', ':'))
    key = settings.lovense_aes_key.encode('utf-8')
    iv = settings.lovense_aes_iv.encode('utf-8')
    if len(iv) != 16:
        raise ValueError('LOVENSE_AES_IV must decode to 16 bytes for AES-CBC')
    if len(key) not in (16, 24, 32):
        raise ValueError('LOVENSE_AES_KEY must be 16, 24, or 32 UTF-8 bytes for AES')

    padder = padding.PKCS7(128).padder()
    padded = padder.update(payload.encode('utf-8')) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode('ascii')
