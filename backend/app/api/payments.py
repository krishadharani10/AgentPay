import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import get_settings, Settings
from app.database import get_db
from app.models.transaction import Transaction
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.schemas.payments import (
    PaymentProviderConfigResponse,
    RazorpayVerifyRequest,
    RazorpayVerifyResponse,
)

router = APIRouter(prefix="/api/payments", tags=["Payments"])


@router.get("/config", response_model=PaymentProviderConfigResponse)
def get_payment_provider_config(
    settings: Settings = Depends(get_settings),
) -> PaymentProviderConfigResponse:
    """
    Returns public payment provider configuration.
    Security Invariant: Strictly returns public key_id only (never exposes key_secret).
    """
    provider = (getattr(settings, "payment_provider", "MOCK") or "MOCK").upper().strip()
    key_id = getattr(settings, "razorpay_key_id", "") or ""

    return PaymentProviderConfigResponse(
        provider=provider,
        key_id=key_id if provider == "RAZORPAY" else None,
        currency="INR",
        is_test_mode=True,
        features={
            "checkout_js": True,
            "direct_upi": True,
            "card_tokenization": True,
            "policy_guard": True,
        },
    )


@router.post("/razorpay/verify", response_model=RazorpayVerifyResponse)
def verify_razorpay_payment(
    request: RazorpayVerifyRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RazorpayVerifyResponse:
    """
    Verifies Razorpay standard checkout payment signature server-side.
    Validates HMAC-SHA256 signature using RAZORPAY_KEY_SECRET.
    Transitions transaction to SUCCESS upon valid signature and persists PaymentAttempt and AuditLog.
    """
    # 1. Fetch transaction
    try:
        tx_uuid = uuid.UUID(request.transaction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transaction_id UUID format: '{request.transaction_id}'.",
        )

    tx = db.get(Transaction, tx_uuid)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{request.transaction_id}' not found.",
        )

    # 2. Verify signature
    key_secret = str(getattr(settings, "razorpay_key_secret", "") or "").strip()
    if not key_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server RAZORPAY_KEY_SECRET is not configured.",
        )

    msg = f"{request.razorpay_order_id}|{request.razorpay_payment_id}"
    generated_signature = hmac.new(
        key_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    is_valid = hmac.compare_digest(generated_signature, request.razorpay_signature)

    now = datetime.now(timezone.utc)

    if not is_valid:
        # Create failed attempt and audit log
        attempt = PaymentAttempt(
            transaction_id=tx.id,
            payment_method_id=tx.payment_method_id,
            attempt_number=1,
            status="FAILED",
            provider_payment_id=request.razorpay_payment_id,
            error_code="SIGNATURE_VERIFICATION_FAILED",
            error_message="Razorpay payment signature mismatch.",
            response_payload={
                "order_id": request.razorpay_order_id,
                "payment_id": request.razorpay_payment_id,
                "error": "Invalid signature",
            },
        )
        db.add(attempt)

        audit = AuditLog(
            agent_id=tx.agent_id,
            transaction_id=tx.id,
            event_type="PAYMENT_VERIFICATION_FAILED",
            action="VERIFY_RAZORPAY_PAYMENT",
            decision="FAILED",
            reason="Razorpay payment signature mismatch.",
            metadata_payload={
                "order_id": request.razorpay_order_id,
                "payment_id": request.razorpay_payment_id,
            },
        )
        db.add(audit)
        db.commit()

        return RazorpayVerifyResponse(
            success=False,
            verified=False,
            transaction_id=str(tx.id),
            status=tx.status,
            provider_payment_id=request.razorpay_payment_id,
            message="Razorpay payment signature verification failed.",
        )

    # 3. Transition Transaction to SUCCESS
    tx.status = "SUCCESS"
    tx.provider_payment_id = request.razorpay_payment_id
    tx.payment_provider = "RAZORPAY"
    tx.updated_at = now

    # Query existing attempts to find matching or calculate next attempt number
    existing_attempts = (
        db.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == tx.id)
            .order_by(PaymentAttempt.attempt_number.desc())
        )
        .scalars()
        .all()
    )

    if existing_attempts:
        # Update the most recent attempt if it is the one being verified
        latest_attempt = existing_attempts[0]
        latest_attempt.status = "SUCCESS"
        latest_attempt.provider_payment_id = request.razorpay_payment_id
        latest_attempt.error_code = None
        latest_attempt.error_message = None
        latest_attempt.response_payload = {
            **(latest_attempt.response_payload or {}),
            "order_id": request.razorpay_order_id,
            "payment_id": request.razorpay_payment_id,
            "signature_verified": True,
            "provider": "RazorpayPaymentProvider",
            "mode": "TEST",
        }
        latest_attempt.updated_at = now
    else:
        # Record new PaymentAttempt
        attempt = PaymentAttempt(
            transaction_id=tx.id,
            payment_method_id=tx.payment_method_id,
            attempt_number=1,
            status="SUCCESS",
            provider_payment_id=request.razorpay_payment_id,
            error_code=None,
            error_message=None,
            response_payload={
                "order_id": request.razorpay_order_id,
                "payment_id": request.razorpay_payment_id,
                "signature_verified": True,
                "provider": "RazorpayPaymentProvider",
                "mode": "TEST",
            },
        )
        db.add(attempt)

    # Record AuditLog
    audit = AuditLog(
        agent_id=tx.agent_id,
        transaction_id=tx.id,
        event_type="PAYMENT_RESULT",
        action="VERIFY_RAZORPAY_PAYMENT",
        decision="SUCCESS",
        reason="Razorpay standard checkout payment verified and captured successfully.",
        metadata_payload={
            "provider": "RAZORPAY",
            "order_id": request.razorpay_order_id,
            "payment_id": request.razorpay_payment_id,
            "amount": float(tx.amount),
            "currency": tx.currency,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(tx)


    return RazorpayVerifyResponse(
        success=True,
        verified=True,
        transaction_id=str(tx.id),
        status="SUCCESS",
        provider_payment_id=request.razorpay_payment_id,
        message="Razorpay payment verified and transaction successfully completed.",
        details={
            "order_id": request.razorpay_order_id,
            "payment_id": request.razorpay_payment_id,
            "amount": float(tx.amount),
            "currency": tx.currency,
        },
    )
