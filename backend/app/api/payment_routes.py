"""Stripe Checkout for token purchases."""

import logging

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_common import current_user_from_auth
from app.api.schemas import (
    CustomPurchaseOptions,
    StripeCheckoutRequest,
    StripeCheckoutResponse,
    StripePackagePublic,
    StripePackagesResponse,
    StripeSessionSyncRequest,
    StripeSessionSyncResponse,
)
from app.db.session import get_db
from app.models.user import User
from app.services.stripe_checkout import (
    create_checkout_session,
    create_checkout_session_custom,
    get_custom_purchase_options,
    get_stripe_publishable_key,
    get_stripe_secret_key,
    list_packages,
    process_checkout_completed,
    stripe_checkout_disabled_reason,
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
    pk = get_stripe_publishable_key()
    enabled = stripe_configured()
    hint = '' if enabled else stripe_checkout_disabled_reason()
    raw_custom = get_custom_purchase_options()
    custom = CustomPurchaseOptions(**raw_custom) if raw_custom else None
    return StripePackagesResponse(
        packages=_public_packages(),
        publishable_key=pk,
        checkout_enabled=enabled,
        payments_hint=hint,
        custom_purchase=custom,
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
        if body.custom_tokens is not None:
            session = create_checkout_session_custom(user=user, tokens=body.custom_tokens)
        else:
            session = create_checkout_session(user=user, package_id=body.package_id or '')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    url = session.url
    if not url:
        raise HTTPException(status_code=502, detail='Stripe did not return a checkout URL')
    return StripeCheckoutResponse(url=url)


@router.post('/payments/stripe/sync-session', response_model=StripeSessionSyncResponse)
def stripe_sync_session(
    body: StripeSessionSyncRequest,
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> StripeSessionSyncResponse:
    """Apply token credit from a completed Checkout Session (same logic as webhook).

    Call this when the browser returns to success_url so the balance updates even if the
    webhook is delayed or misconfigured. Idempotent per session id.
    """
    if not stripe_configured():
        raise HTTPException(status_code=503, detail='Stripe payments are not configured')
    user = current_user_from_auth(authorization, db, required=True)
    assert user is not None
    sid = body.session_id.strip()
    if not sid.startswith('cs_'):
        raise HTTPException(status_code=400, detail='Invalid session_id')
    stripe.api_key = get_stripe_secret_key()
    try:
        sess = stripe.checkout.Session.retrieve(sid)
    except stripe.StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or 'Could not load Stripe session') from exc
    if isinstance(sess, dict):
        d = sess
    elif hasattr(sess, 'to_dict'):
        d = sess.to_dict()
    else:
        d = dict(sess)
    if d.get('payment_status') != 'paid':
        raise HTTPException(status_code=400, detail='Payment not completed')
    if str(d.get('client_reference_id') or '') != str(user.id):
        raise HTTPException(status_code=403, detail='This purchase belongs to another account')
    meta = d.get('metadata') or {}
    if str(meta.get('user_id') or '') != str(user.id):
        raise HTTPException(status_code=403, detail='This purchase belongs to another account')
    try:
        process_checkout_completed(db, d)
    except IntegrityError:
        db.rollback()
        log.info('stripe sync-session duplicate or race sid=%s', sid)
    db.refresh(user)
    return StripeSessionSyncResponse(token_balance=int(user.token_balance))


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
