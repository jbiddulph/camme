"""Stripe Checkout Sessions for token packs + webhook credit."""

from __future__ import annotations

import json
import logging
import math
import os
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


def _normalize_secret(value: str | None) -> str:
    if value is None:
        return ''
    s = str(value).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
        s = s[1:-1].strip()
    return s


def get_stripe_secret_key() -> str:
    """
    Stripe secret for API calls.

    Prefer os.environ['STRIPE_SECRET_KEY'] first so Heroku/Render Config Vars always win
    over any odd .env interaction. (Python uses os.environ — there is no process.env.)
    """
    for candidate in (os.environ.get('STRIPE_SECRET_KEY'), settings.stripe_secret_key):
        n = _normalize_secret(candidate)
        if n:
            return n
    return ''


def stripe_configured() -> bool:
    """True if a usable Stripe secret is set (standard or restricted key)."""
    k = get_stripe_secret_key()
    if not k:
        return False
    return k.startswith(('sk_live_', 'sk_test_', 'rk_live_', 'rk_test_'))


def get_stripe_publishable_key() -> str:
    """Prefer env var (Heroku Config Vars) then Settings."""
    for candidate in (os.environ.get('STRIPE_PUBLISHABLE_KEY'), settings.stripe_publishable_key):
        n = _normalize_secret(candidate)
        if n:
            return n
    return ''


def stripe_checkout_disabled_reason() -> str:
    """Human-readable reason when checkout_enabled is false (no full secrets exposed)."""
    if stripe_configured():
        return ''
    if 'STRIPE_SECRET_KEY' not in os.environ:
        return (
            'This API process has no STRIPE_SECRET_KEY in its environment. '
            'Add it to the FastAPI host (e.g. Heroku: heroku config:set STRIPE_SECRET_KEY=sk_test_… -a camme-api), '
            'then restart that app. Setting vars only on the Go/web dyno does not reach this endpoint.'
        )
    raw = os.environ.get('STRIPE_SECRET_KEY', '')
    if not str(raw).strip():
        return 'STRIPE_SECRET_KEY is set but empty — remove it or set a full sk_test_… / sk_live_… value.'
    k = get_stripe_secret_key()
    if not k:
        return 'STRIPE_SECRET_KEY could not be read after normalization — check for stray quotes or newlines in Config Vars.'
    if not k.startswith(('sk_live_', 'sk_test_', 'rk_live_', 'rk_test_')):
        return (
            'STRIPE_SECRET_KEY must start with sk_test_, sk_live_, rk_test_, or rk_live_. '
            f'Current value length is {len(k)} (first characters: {k[:3]!r}…).'
        )
    return 'Stripe checkout is disabled for an unknown reason — check API logs.'


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


def custom_purchase_min_tokens() -> int:
    g = float(settings.stripe_gbp_per_token_purchase)
    if g <= 0:
        return 1
    return max(1, math.ceil(float(settings.stripe_minimum_charge_gbp) / g))


def get_custom_purchase_options() -> dict[str, Any] | None:
    if not stripe_configured():
        return None
    g = float(settings.stripe_gbp_per_token_purchase)
    return {
        'min_tokens': custom_purchase_min_tokens(),
        'max_tokens': int(settings.stripe_custom_tokens_max),
        'gbp_per_token': g,
        'currency': 'gbp',
    }


def _create_stripe_checkout_session(
    *,
    user: User,
    tokens: int,
    unit_amount_pence: int,
    currency: str,
    product_name: str,
    package_id_meta: str,
) -> stripe.checkout.Session:
    stripe.api_key = get_stripe_secret_key()
    base = settings.stripe_frontend_base_url.rstrip('/')

    return stripe.checkout.Session.create(
        mode='payment',
        line_items=[
            {
                'price_data': {
                    'currency': currency,
                    'unit_amount': unit_amount_pence,
                    'product_data': {
                        'name': product_name,
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
            'package_id': package_id_meta,
        },
    )


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

    return _create_stripe_checkout_session(
        user=user,
        tokens=tokens,
        unit_amount_pence=unit_amount,
        currency=currency,
        product_name=label,
        package_id_meta=str(pkg.get('id', '')),
    )


def create_checkout_session_custom(*, user: User, tokens: int) -> stripe.checkout.Session:
    if not stripe_configured():
        raise RuntimeError('Stripe secret key is not configured')

    g = float(settings.stripe_gbp_per_token_purchase)
    if g <= 0:
        raise ValueError('Invalid stripe_gbp_per_token_purchase')

    min_t = custom_purchase_min_tokens()
    if tokens < min_t:
        raise ValueError(
            f'At least {min_t} tokens required (minimum card charge ≈ £{settings.stripe_minimum_charge_gbp:.2f}).'
        )
    if tokens > settings.stripe_custom_tokens_max:
        raise ValueError(f'At most {settings.stripe_custom_tokens_max} tokens per purchase.')

    unit_amount = int(round(tokens * g * 100))
    currency = 'gbp'
    label = f'{tokens} tokens (custom)'
    return _create_stripe_checkout_session(
        user=user,
        tokens=tokens,
        unit_amount_pence=unit_amount,
        currency=currency,
        product_name=label,
        package_id_meta='custom',
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
    stripe.api_key = get_stripe_secret_key()
    return stripe.Webhook.construct_event(
        payload, sig_header or '', settings.stripe_webhook_secret.strip()
    )
