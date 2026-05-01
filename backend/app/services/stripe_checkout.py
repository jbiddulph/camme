"""Stripe Checkout Sessions for token packs + webhook credit."""

from __future__ import annotations

import json
import logging
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.token_purchase import TokenPurchase
from app.models.user import User

log = logging.getLogger('uvicorn.error')

DEFAULT_PACKAGES: list[dict[str, Any]] = [
    {
        'id': 't100',
        'label': '100 tokens',
        'tokens': 100,
        'unit_amount': 499,
        'currency': 'gbp',
    },
    {
        'id': 't500',
        'label': '500 tokens',
        'tokens': 500,
        'unit_amount': 1999,
        'currency': 'gbp',
    },
    {
        'id': 't1200',
        'label': '1,200 tokens',
        'tokens': 1200,
        'unit_amount': 3999,
        'currency': 'gbp',
    },
]


def stripe_configured() -> bool:
    k = (settings.stripe_secret_key or '').strip()
    return bool(k and k.startswith('sk_'))


def list_packages() -> list[dict[str, Any]]:
    raw = (settings.stripe_packages_json or '').strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return data
        except json.JSONDecodeError:
            log.warning('STRIPE_PACKAGES_JSON invalid JSON; using defaults')
    return list(DEFAULT_PACKAGES)


def find_package(package_id: str) -> dict[str, Any] | None:
    pid = package_id.strip()
    for p in list_packages():
        if p.get('id') == pid:
            return p
    return None


def create_checkout_session(*, user: User, package_id: str) -> stripe.checkout.Session:
    if not stripe_configured():
        raise RuntimeError('Stripe secret key is not configured')

    pkg = find_package(package_id)
    if not pkg:
        raise ValueError('Unknown package')

    tokens = int(pkg['tokens'])
    if tokens < 1:
        raise ValueError('Invalid token amount')

    unit_amount = int(pkg['unit_amount'])
    currency = str(pkg.get('currency') or 'gbp').lower()
    label = str(pkg.get('label') or f'{tokens} tokens')

    stripe.api_key = settings.stripe_secret_key.strip()
    base = settings.stripe_frontend_base_url.rstrip('/')

    return stripe.checkout.Session.create(
        mode='payment',
        line_items=[
            {
                'price_data': {
                    'currency': currency,
                    'unit_amount': unit_amount,
                    'product_data': {
                        'name': label,
                        'description': f'Tokens for tipping on {settings.site_display_name} ({tokens} tokens)',
                    },
                },
                'quantity': 1,
            }
        ],
        success_url=f'{base}/buy-tokens?paid=1&session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{base}/buy-tokens?canceled=1',
        client_reference_id=str(user.id),
        metadata={
            'user_id': str(user.id),
            'tokens': str(tokens),
            'package_id': str(pkg.get('id', '')),
        },
    )


def process_checkout_completed(db: Session, session_obj: dict[str, Any]) -> None:
    session_id = session_obj.get('id')
    if not session_id:
        return

    existing = db.scalar(
        select(TokenPurchase).where(TokenPurchase.stripe_checkout_session_id == session_id)
    )
    if existing:
        return

    meta = session_obj.get('metadata') or {}
    uid_raw = meta.get('user_id')
    tokens_raw = meta.get('tokens')
    if not uid_raw or not tokens_raw:
        log.warning('Stripe session %s missing metadata', session_id)
        return

    try:
        user_id = int(uid_raw)
        tokens = int(tokens_raw)
    except (TypeError, ValueError):
        log.warning('Stripe session %s bad metadata', session_id)
        return

    if tokens < 1:
        return

    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        log.warning('Stripe session %s user %s not found', session_id, user_id)
        return

    amount_total = session_obj.get('amount_total')
    currency = session_obj.get('currency')

    user.token_balance = int(user.token_balance) + tokens
    db.add(
        TokenPurchase(
            user_id=user_id,
            stripe_checkout_session_id=session_id,
            tokens_granted=tokens,
            amount_total=int(amount_total) if amount_total is not None else None,
            currency=str(currency) if currency else None,
        )
    )
    db.commit()
    log.info('Credited %s tokens to user %s (session %s)', tokens, user_id, session_id)


def verify_webhook_payload(payload: bytes, sig_header: str | None) -> stripe.Event:
    if not (settings.stripe_webhook_secret or '').strip():
        raise RuntimeError('STRIPE_WEBHOOK_SECRET is not configured')
    stripe.api_key = settings.stripe_secret_key.strip()
    return stripe.Webhook.construct_event(
        payload, sig_header or '', settings.stripe_webhook_secret.strip()
    )
