import uuid
import re
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.tools import (
    get_wallet_policy,
    get_bill,
    evaluate_payment,
    create_payment,
    get_payment_status,
    retry_payment,
)
from app.agents.llm_provider import LLMProvider, MockLLMProvider
from app.schemas.agent_types import (
    TransactionIntent,
    AgentDecision,
    PaymentRequest,
    AgentResponse,
)
from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.services.payment_adapter import PaymentAdapter, MockPaymentAdapter


class AgentOrchestrator:
    """
    Deterministic Agent Orchestrator for AgentPay.
    Coordinates the end-to-end payment lifecycle:
    User Request -> Tool Selection -> Bill Lookup -> Policy Evaluation -> Payment Execution / Failure Handling.
    """

    def __init__(
        self,
        adapter: Optional[PaymentAdapter] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.adapter = adapter or MockPaymentAdapter()
        self.llm_provider = llm_provider or MockLLMProvider()

    def process_request(
        self,
        db: Session,
        *,
        message: str,
        agent_id: Optional[uuid.UUID] = None,
        bill_id: Optional[uuid.UUID] = None,
        merchant_name: Optional[str] = None,
        amount: Optional[float] = None,
        category: Optional[str] = None,
        force_failure: bool = False,
        retry_if_failed: bool = False,
    ) -> Dict[str, Any]:
        """
        Orchestrates an agent payment request through deterministic tool flow.
        """
        audit_trail: List[Dict[str, Any]] = []

        # 1. TOOL CALL: GET_BILL (Find target bill or extract payment details)
        target_bill = None
        if bill_id:
            target_bill = get_bill(db, bill_id=bill_id)
        elif merchant_name:
            target_bill = get_bill(db, merchant_name=merchant_name)
        else:
            # Match keywords from user message
            target_bill = get_bill(db, query=message)

        # Fallback or explicit parameters if no saved bill
        if target_bill and not amount:
            resolved_merchant = target_bill["merchant_name"]
            resolved_amount = float(target_bill["amount"])
            resolved_category = target_bill["category"]
            resolved_bill_id = uuid.UUID(target_bill["bill_id"])
        else:
            resolved_merchant = merchant_name or self._extract_merchant(message)
            resolved_amount = float(amount or self._extract_amount(message) or 1000.0)
            resolved_category = category or self._extract_category(message, resolved_merchant)
            resolved_bill_id = bill_id

        audit_trail.append({
            "step": "get_bill",
            "details": {
                "merchant": resolved_merchant,
                "amount": resolved_amount,
                "category": resolved_category,
                "bill_id": str(resolved_bill_id) if resolved_bill_id else None,
            },
        })

        # 2. TOOL CALL: GET_WALLET_POLICY
        wallet_policy = get_wallet_policy(db, agent_id=agent_id)
        audit_trail.append({
            "step": "get_wallet_policy",
            "details": {
                "wallet_status": wallet_policy["wallet_status"],
                "remaining_budget": wallet_policy["remaining_daily_budget"],
                "per_tx_limit": wallet_policy["per_transaction_limit"],
            },
        })

        # 3. TOOL CALL: EVALUATE_PAYMENT (Mandatory Deterministic Policy Boundary)
        eval_request = {
            "merchant_name": resolved_merchant,
            "amount": resolved_amount,
            "category": resolved_category,
            "agent_id": agent_id,
            "idempotency_key": f"agent_run_{uuid.uuid4().hex[:12]}",
            "metadata": {"user_message": message, "force_failure": force_failure},
        }
        eval_result = evaluate_payment(db, eval_request)
        audit_trail.append({
            "step": "evaluate_payment",
            "allowed": eval_result["allowed"],
            "decision_code": eval_result["decision_code"],
            "reason": eval_result["reason"],
        })

        # 4. DECISION BRANCH: IF DENIED -> STOP IMMEDIATELY
        if not eval_result["allowed"]:
            return {
                "success": False,
                "decision": "DENIED",
                "decision_code": eval_result["decision_code"],
                "message": f"Payment of ₹{resolved_amount:,.2f} for '{resolved_merchant}' was DENIED by policy: {eval_result['reason']}",
                "payment_id": None,
                "payment_status": "REJECTED",
                "rules_checked": eval_result["rules_checked"],
                "remaining_daily_budget": eval_result["remaining_daily_budget"],
                "audit_trail": audit_trail,
            }

        # 5. DECISION BRANCH: IF ALLOWED -> CREATE_PAYMENT
        payment_request = {
            "merchant_name": resolved_merchant,
            "amount": resolved_amount,
            "category": resolved_category,
            "agent_id": agent_id,
            "bill_id": resolved_bill_id,
            "idempotency_key": eval_request["idempotency_key"],
            "metadata": {"user_message": message, "force_failure": force_failure},
        }
        payment_result = create_payment(db, payment_request, adapter=self.adapter)
        audit_trail.append({
            "step": "create_payment",
            "status": payment_result.get("status"),
            "payment_id": payment_result.get("payment_id"),
        })

        payment_id_str = payment_result.get("payment_id")

        # 6. TOOL CALL: GET_PAYMENT_STATUS
        if payment_id_str:
            status_data = get_payment_status(db, uuid.UUID(payment_id_str))
            audit_trail.append({
                "step": "get_payment_status",
                "status": status_data["status"],
                "attempt": status_data["attempt"],
            })

        # 7. FAILURE & RETRY HANDLING
        if payment_result.get("status") == "FAILED" and retry_if_failed and payment_id_str:
            # Execute retry
            retry_result = retry_payment(
                db,
                payment_id=uuid.UUID(payment_id_str),
                adapter=self.adapter,
                metadata={"user_message": message, "force_failure": False},  # retry without force_failure
            )
            audit_trail.append({
                "step": "retry_payment",
                "status": retry_result.get("status"),
                "attempt": retry_result.get("attempt_number"),
            })
            payment_result = retry_result

        final_status = payment_result.get("status")
        is_success = (final_status == "SUCCESS")

        if is_success:
            user_message = f"Payment of ₹{resolved_amount:,.2f} to {resolved_merchant} was authorized and completed successfully."
        else:
            user_message = f"Payment of ₹{resolved_amount:,.2f} to {resolved_merchant} was authorized but failed at payment gateway: {payment_result.get('error_message')}"

        return {
            "success": is_success,
            "decision": "ALLOWED",
            "decision_code": "APPROVED",
            "message": user_message,
            "payment_id": payment_result.get("payment_id"),
            "provider_payment_id": payment_result.get("provider_payment_id"),
            "payment_status": final_status,
            "amount": resolved_amount,
            "merchant_name": resolved_merchant,
            "rules_checked": eval_result["rules_checked"],
            "remaining_daily_budget": eval_result["remaining_daily_budget"],
            "audit_trail": audit_trail,
        }

    def _extract_merchant(self, message: str) -> str:
        msg_lower = message.lower()
        if "torrent" in msg_lower or "electricity" in msg_lower or "power" in msg_lower:
            return "Torrent Power"
        elif "netflix" in msg_lower:
            return "Netflix"
        elif "spotify" in msg_lower or "music" in msg_lower:
            return "Spotify"
        elif "makemytrip" in msg_lower or "flight" in msg_lower or "travel" in msg_lower:
            return "MakeMyTrip"
        elif "amazon" in msg_lower or "shopping" in msg_lower:
            return "Amazon"
        elif "crypto" in msg_lower:
            return "Crypto Exchange"
        return "Unknown Merchant"

    def _extract_category(self, message: str, merchant_name: str) -> str:
        msg_lower = message.lower()
        if "crypto" in msg_lower:
            return "crypto"
        if "gambling" in msg_lower or "casino" in msg_lower:
            return "gambling"
        
        merch_lower = merchant_name.lower()
        if "torrent" in merch_lower or "electricity" in msg_lower:
            return "utilities"
        elif "netflix" in merch_lower or "spotify" in merch_lower:
            return "subscriptions"
        elif "makemytrip" in merch_lower or "travel" in msg_lower:
            return "travel"
        elif "amazon" in merch_lower:
            return "shopping"
        return "general"

    def _extract_amount(self, message: str) -> Optional[float]:
        # Match ₹1,240 or 1240 or Rs 1240 or $1240
        match = re.search(r'(?:₹|rs\.?|inr|\$)?\s*(\d+(?:,\d+)*(?:\.\d+)?)', message, re.IGNORECASE)
        if match:
            clean_num = match.group(1).replace(",", "")
            try:
                val = float(clean_num)
                if val > 0:
                    return val
            except ValueError:
                pass
        return None

    # ──────────────────────────────────────────────────────────────────────
    # DAY 2 PHASE 1 — LLM-based Agent Flow
    # ──────────────────────────────────────────────────────────────────────

    def process_with_llm(
        self,
        db: Session,
        *,
        message: str,
        agent_id: Optional[uuid.UUID] = None,
        force_failure: bool = False,
        retry_if_failed: bool = False,
    ) -> AgentResponse:
        """
        Process a natural-language payment request using the LLM abstraction layer.

        Flow:
            1. LLMProvider.parse_payment_intent(message) → TransactionIntent
            2. get_bill (optional lookup)
            3. get_wallet_policy
            4. evaluate_payment → AgentDecision (deterministic Policy Engine)
            5. If DENIED → return explanation, stop
            6. If APPROVED → PaymentRequest → create_payment → AgentResponse
            7. Record agent-level audit events at each step

        SECURITY: The LLM only produces TransactionIntent — it never
        touches the Policy Engine, PaymentService, or PaymentAdapter directly.
        """
        audit_trail: List[Dict[str, Any]] = []

        # Resolve agent for audit logging
        if agent_id:
            agent = db.get(Agent, agent_id)
        else:
            agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()

        resolved_agent_id = agent.id if agent else None

        # ── Step 1: AUDIT — Agent request received ──
        self._record_agent_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="AGENT_REQUEST",
            action="RECEIVE_REQUEST",
            decision="RECEIVED",
            reason=f"Agent received payment request: {message[:200]}",
            metadata_payload={"user_message": message},
        )
        audit_trail.append({"step": "agent_request", "message": message[:200]})

        # ── Step 2: LLM converts natural language → TransactionIntent ──
        intent: TransactionIntent = self.llm_provider.parse_payment_intent(message)

        amount_display = f"₹{intent.amount:,.2f}" if intent.amount is not None else "(amount lookup pending)"
        self._record_agent_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="INTENT_CREATED",
            action="PARSE_INTENT",
            decision="PARSED",
            reason=f"Parsed intent: {intent.merchant} {amount_display} ({intent.category})",
            metadata_payload=intent.model_dump(),
        )
        audit_trail.append({
            "step": "intent_created",
            "intent": intent.model_dump(),
        })

        # ── Step 3: Get bill info (lookup and amount resolution from DB) ──
        target_bill = None
        if intent.bill_id:
            try:
                target_bill = get_bill(db, bill_id=uuid.UUID(intent.bill_id))
            except (ValueError, TypeError):
                pass
        if not target_bill and intent.merchant and intent.merchant != "Unknown Merchant":
            target_bill = get_bill(db, merchant_name=intent.merchant)
        if not target_bill:
            target_bill = get_bill(db, query=message)

        if target_bill:
            # If user did not specify amount in message, retrieve amount dynamically from database bill
            resolved_amount = intent.amount if intent.amount is not None else float(target_bill["amount"])
            intent = TransactionIntent(
                merchant=target_bill["merchant_name"],
                amount=resolved_amount,
                currency=target_bill.get("currency", intent.currency),
                category=target_bill.get("category", intent.category),
                description=intent.description or target_bill.get("description", ""),
                bill_id=target_bill.get("bill_id"),
            )
        elif intent.amount is None:
            intent.amount = 1000.0

        audit_trail.append({
            "step": "get_bill",
            "found": target_bill is not None,
            "resolved_amount": intent.amount,
            "bill_id": intent.bill_id,
        })

        # ── Step 4: Get wallet policy ──
        wallet_policy = get_wallet_policy(db, agent_id=agent_id)
        audit_trail.append({
            "step": "get_wallet_policy",
            "wallet_status": wallet_policy["wallet_status"],
            "remaining_budget": wallet_policy["remaining_daily_budget"],
        })

        # ── Step 5: MANDATORY — Deterministic Policy Evaluation ──
        idempotency_key = f"agent_llm_{uuid.uuid4().hex[:12]}"
        eval_request = {
            "merchant_name": intent.merchant,
            "amount": intent.amount,
            "category": intent.category,
            "agent_id": agent_id,
            "idempotency_key": idempotency_key,
            "metadata": {"user_message": message, "force_failure": force_failure},
        }
        eval_result = evaluate_payment(db, eval_request)

        # ── Construct typed AgentDecision ──
        decision = AgentDecision(
            allowed=eval_result["allowed"],
            decision_code=eval_result["decision_code"],
            reason=eval_result["reason"],
            policy_checks=eval_result["rules_checked"],
        )
        audit_trail.append({
            "step": "evaluate_payment",
            "allowed": decision.allowed,
            "decision_code": decision.decision_code,
            "reason": decision.reason,
        })

        # ── Step 6: DECISION BRANCH ──
        if not decision.allowed:
            # DENIED — PaymentService is NEVER called
            explanation = (
                f"Payment of ₹{intent.amount:,.2f} to '{intent.merchant}' was DENIED. "
                f"Reason: {decision.reason}"
            )
            return AgentResponse(
                success=False,
                decision="DENIED",
                message=explanation,
                payment_status="REJECTED",
                payment_id=None,
                explanation=explanation,
                decision_code=decision.decision_code,
                amount=intent.amount,
                merchant_name=intent.merchant,
                rules_checked=eval_result["rules_checked"],
                remaining_daily_budget=eval_result["remaining_daily_budget"],
                audit_trail=audit_trail,
            )

        # ── Step 7: APPROVED — Create PaymentRequest and execute ──
        bill_uuid = None
        if intent.bill_id:
            try:
                bill_uuid = uuid.UUID(intent.bill_id)
            except (ValueError, TypeError):
                pass

        payment_req = PaymentRequest(
            merchant_name=intent.merchant,
            amount=intent.amount,
            currency=intent.currency,
            category=intent.category,
            agent_id=agent_id,
            bill_id=bill_uuid,
            idempotency_key=idempotency_key,
            metadata={"user_message": message, "force_failure": force_failure},
        )

        payment_result = create_payment(
            db, payment_req.model_dump(mode="json"), adapter=self.adapter,
        )
        audit_trail.append({
            "step": "create_payment",
            "status": payment_result.get("status"),
            "payment_id": payment_result.get("payment_id"),
        })

        payment_id_str = payment_result.get("payment_id")

        # ── Step 8: Get payment status ──
        if payment_id_str:
            status_data = get_payment_status(db, uuid.UUID(payment_id_str))
            audit_trail.append({
                "step": "get_payment_status",
                "status": status_data["status"],
                "attempt": status_data["attempt"],
            })

        # ── Step 9: Retry handling ──
        if payment_result.get("status") == "FAILED" and retry_if_failed and payment_id_str:
            retry_result = retry_payment(
                db,
                payment_id=uuid.UUID(payment_id_str),
                adapter=self.adapter,
                metadata={"user_message": message, "force_failure": False},
            )
            audit_trail.append({
                "step": "retry_payment",
                "status": retry_result.get("status"),
                "attempt": retry_result.get("attempt_number"),
            })
            payment_result = retry_result

        # ── Build final AgentResponse ──
        final_status = payment_result.get("status")
        is_success = (final_status == "SUCCESS")

        if is_success:
            user_message = (
                f"Payment of ₹{intent.amount:,.2f} to {intent.merchant} "
                f"was authorized and completed successfully."
            )
        else:
            user_message = (
                f"Payment of ₹{intent.amount:,.2f} to {intent.merchant} "
                f"was authorized but failed at payment gateway: "
                f"{payment_result.get('error_message')}"
            )

        return AgentResponse(
            success=is_success,
            decision="ALLOWED",
            message=user_message,
            payment_status=final_status,
            payment_id=payment_result.get("payment_id"),
            explanation=user_message,
            decision_code="APPROVED",
            amount=intent.amount,
            merchant_name=intent.merchant,
            provider_payment_id=payment_result.get("provider_payment_id"),
            rules_checked=eval_result["rules_checked"],
            remaining_daily_budget=eval_result["remaining_daily_budget"],
            audit_trail=audit_trail,
        )

    def _record_agent_audit(
        self,
        db: Session,
        *,
        agent_id: Optional[uuid.UUID],
        event_type: str,
        action: str,
        decision: str,
        reason: str,
        metadata_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an agent-level audit event in the existing AuditLog table."""
        audit_entry = AuditLog(
            agent_id=agent_id,
            transaction_id=None,
            event_type=event_type,
            action=action,
            decision=decision,
            reason=reason,
            metadata_payload=metadata_payload,
        )
        db.add(audit_entry)
        db.commit()
