"""Stripe Checkout for token purchases."""

import logging

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_common import current_user_from_auth
from app.api.schemas import (
    StripeCheckoutRequest,
    StripeCheckoutResponse,
    StripePackagePublic,
    StripePackagesResponse,
)
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.stripe_checkout import (
    create_checkout_session,
    list_packages,
    process_checkout_completed,
    stripe_configured,
    verify_webhook_payload,
)

log = logging.getLogger('uvicorn.error')

router = APIRouter(tags=['payments'])


def _public_packages() -> list[StripePackagePublic]:
    out: list[StripePackagePublic] = []
    for p in list_packages():
        try:
            tokens = int(p['tokens'])
            out.append(
                StripePackagePublic(
                    id=str(p['id']),
                    label=str(p.get('label') or f'{tokens} tokens'),
                    tokens=tokens,
                    unit_amount=int(p['unit_amount']),
                    currency=str(p.get('currency') or 'gbp').lower(),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.warning('skip invalid stripe package %r: %s', p, exc)
    return out


@router.get('/payments/stripe/packages', response_model=StripePackagesResponse)
def stripe_packages_public() -> StripePackagesResponse:
    pk = (settings.stripe_publishable_key or '').strip()
    return StripePackagesResponse(
        packages=_public_packages(),
        publishable_key=pk,
        checkout_enabled=stripe_configured(),
    )


@router.post('/payments/stripe/checkout', response_model=StripeCheckoutResponse)
def stripe_create_checkout(
    body: StripeCheckoutRequest,
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> StripeCheckoutResponse:
    if not stripe_configured():
        raise HTTPException(status_code=503, detail='Stripe payments are not configured')
    user = current_user_from_auth(authorization, db, required=True)
    assert user is not None
    try:
        session = create_checkout_session(user=user, package_id=body.package_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    url = session.url
    if not url:
        raise HTTPException(status_code=502, detail='Stripe did not return a checkout URL')
    return StripeCheckoutResponse(url=url)


@router.post('/payments/stripe/webhook')
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = await request.body()
    sig = request.headers.get('stripe-signature')
    try:
        event = verify_webhook_payload(payload, sig)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail='Invalid Stripe signature')

    evt_type = getattr(event, 'type', None) or (event.get('type') if isinstance(event, dict) else None)
    if evt_type != 'checkout.session.completed':
        return {'received': True}

    obj = event.data.object
    if isinstance(obj, dict):
        d = obj
    elif hasattr(obj, 'to_dict'):
        d = obj.to_dict()
    else:
        d = {}

    if d.get('payment_status') != 'paid':
        return {'received': True}

    try:
        process_checkout_completed(db, d)
    except IntegrityError:
        db.rollback()
        log.info('stripe session already credited (duplicate webhook)')
    except Exception:
        log.exception('stripe webhook processing failed')
        raise HTTPException(status_code=500, detail='Webhook processing failed') from None

    return {'received': True}
