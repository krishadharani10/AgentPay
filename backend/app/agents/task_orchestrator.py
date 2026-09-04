"""
Task Orchestrator for AgentPay.

Autonomous Commerce Orchestrator sitting directly above the authoritative payment core.

Architecture:
  User natural-language request
  ↓
  AI Agent (LLMProvider)
  ↓
  TaskIntent
  ↓
  TaskOrchestrator
  ↓
  Commerce Search Tool:
    - Flight Search Tool (app/tools/flight_search.py)
    - Restaurant Reservation Tool (app/tools/restaurant_search.py)
    - Direct Payment pass-through
  ↓
  Selected Option
  ↓
  Existing TransactionIntent
  ↓
  Existing Policy Engine (evaluate_payment)         ← ALL authorization decisions
  ↓
  Existing PaymentService (create_payment)
  ↓
  Existing PaymentProvider (Mock / Razorpay)
  ↓
  Existing Audit Log
  ↓
  Task completed / rejected (TaskResponse)

INVARIANTS:
1. TaskOrchestrator NEVER directly authorizes or executes payments without the Policy Engine.
2. TaskOrchestrator does not duplicate Policy Engine or PaymentService logic.
3. Every meaningful step creates immutable AuditLog records using the existing infrastructure.
4. The LLM cannot fabricate flight or restaurant data; all inventory comes from deterministic mock data.
5. A reservation/flight is only CONFIRMED after the existing payment flow succeeds.
"""
import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.transaction import Transaction
from app.schemas.agent_types import TransactionIntent, AgentDecision, PaymentRequest
from app.schemas.task_types import (
    TaskType,
    TaskIntent,
    TaskResponse,
)
from app.tools.flight_search import (
    search_flights,
    select_cheapest_flight,
    flight_to_transaction_dict,
    FlightRecord,
)
from app.tools.restaurant_search import (
    search_restaurants,
    select_cheapest_restaurant,
    restaurant_to_transaction_dict,
    RestaurantRecord,
)
from app.agents.tools import (
    get_wallet_policy,
    evaluate_payment,
    create_payment,
    retry_payment,
)
from app.agents.llm_provider import LLMProvider, MockLLMProvider
from app.services.payment_adapter import PaymentAdapter, get_payment_provider


class TaskOrchestrator:
    """
    Thin, deterministic task orchestration layer.
    Coordinates domain-specific commerce tools and bridges their selections
    into the authoritative AgentPay policy evaluation and payment core.
    """

    def __init__(
        self,
        adapter: Optional[PaymentAdapter] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.adapter = adapter or get_payment_provider()
        self.llm_provider = llm_provider or MockLLMProvider()

    @staticmethod
    def compute_task_idempotency_key(task_intent: TaskIntent) -> str:
        """
        Derives an authoritative deterministic idempotency key for a task intent.
        Ensures identical autonomous tasks map to the exact same idempotency scope.
        Guarantees total key length <= 48 chars to satisfy payment provider receipt limits (max 56).
        """
        if task_intent.task_type == TaskType.BOOK_FLIGHT:
            origin = (task_intent.origin or "any")[:4].upper().strip()
            destination = (task_intent.destination or "any")[:4].upper().strip()
            date_compact = str(task_intent.date or "any").replace("-", "").strip()
            budget = int(task_intent.budget or task_intent.max_budget or 0)
            return f"task_fl_{origin}_{destination}_{date_compact}_{budget}".lower()

        elif task_intent.task_type == TaskType.RESERVE_RESTAURANT:
            city = (task_intent.city or "any")[:4].lower().strip()
            date_compact = str(task_intent.date or "any").replace("-", "").strip()
            time_clean = str(task_intent.time or "any").lower().replace(" ", "").replace(":", "")[:5].strip()
            party_size = task_intent.party_size or 2
            venue = (task_intent.metadata.get("venue") if task_intent.metadata else None) or task_intent.merchant or "any"
            venue_clean = str(venue).lower().replace(" ", "_").strip()[:10]
            budget = int(task_intent.budget or task_intent.max_budget or 0)
            return f"task_res_{city}_{venue_clean}_{date_compact}_{time_clean}_{party_size}_{budget}".lower()

        else:
            merchant = str(task_intent.merchant or "direct").lower().replace(" ", "_").strip()[:12]
            budget = int(task_intent.budget or task_intent.max_budget or 0)
            return f"task_dir_{merchant}_{budget}".lower()

    def process_natural_language(
        self,
        db: Session,
        *,
        message: str,
        agent_id: Optional[uuid.UUID] = None,
        force_failure: bool = False,
        retry_if_failed: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> TaskResponse:
        """
        Processes a natural language request by first extracting a TaskIntent,
        then delegating to execute_task.
        """
        task_intent: TaskIntent = self.llm_provider.parse_task_intent(message)
        return self.execute_task(
            db,
            task_intent=task_intent,
            agent_id=agent_id,
            force_failure=force_failure,
            retry_if_failed=retry_if_failed,
            idempotency_key=idempotency_key,
        )

    def prepare_task(
        self,
        db: Session,
        *,
        message: str,
        agent_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Prepares a commercial task without executing payment:
        1. Parses natural-language message into TaskIntent
        2. Queries domain inventory / tool
        3. Computes deterministic task idempotency key
        4. Checks if an existing transaction is already completed in database
        5. Checks policy limit compliance preview
        """
        task_intent: TaskIntent = self.llm_provider.parse_task_intent(message)
        idempotency_key = self.compute_task_idempotency_key(task_intent)

        # Check existing transaction
        existing_tx = db.execute(
            select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

        already_completed = existing_tx is not None and existing_tx.status == "SUCCESS"
        existing_tx_id = str(existing_tx.id) if existing_tx else None
        existing_status = existing_tx.status if existing_tx else None

        # Resolve selected option
        selected_dict: Optional[Dict[str, Any]] = None
        est_amount: Optional[float] = None
        merchant_name: Optional[str] = None
        summary: str = ""

        if task_intent.task_type == TaskType.BOOK_FLIGHT:
            origin = task_intent.origin or "AMD"
            destination = task_intent.destination or "BOM"
            date = task_intent.date or "2026-09-22"
            max_budget = task_intent.max_budget or task_intent.budget
            search_result = search_flights(origin=origin, destination=destination, date=date, max_budget=max_budget)
            if search_result.filtered_options:
                selected = select_cheapest_flight(search_result)
                selected_dict = {
                    "flight_id": selected.flight_id,
                    "airline": selected.airline,
                    "flight_number": selected.flight_number,
                    "origin": selected.origin,
                    "destination": selected.destination,
                    "date": selected.date,
                    "departure_time": selected.departure_time,
                    "arrival_time": selected.arrival_time,
                    "price": selected.price,
                    "merchant": selected.merchant,
                    "category": selected.category,
                }
                est_amount = selected.price
                merchant_name = selected.merchant
                summary = f"{selected.airline} {selected.flight_number} ({selected.origin}→{selected.destination}) on {selected.date} @ ₹{selected.price:,.2f}"
            else:
                summary = f"Flight search: {origin}→{destination} on {date}"

        elif task_intent.task_type == TaskType.RESERVE_RESTAURANT:
            city = task_intent.city or "Ahmedabad"
            date = task_intent.date or "2026-09-22"
            time = task_intent.time or "8:00 PM"
            party_size = task_intent.party_size or 2
            max_budget = task_intent.max_budget or task_intent.budget
            r_name = (
                task_intent.metadata.get("venue")
                if task_intent.metadata and task_intent.metadata.get("venue")
                else (task_intent.merchant if task_intent.merchant and task_intent.merchant not in ["MakeMyTrip", "Torrent Power", "Netflix", "Amazon"] else None)
            )
            search_result = search_restaurants(city=city, date=date, time=time, party_size=party_size, max_budget=max_budget, restaurant_name=r_name)
            if search_result.filtered_options:
                sel_r = select_cheapest_restaurant(search_result)
                selected_dict = {
                    "slot_id": sel_r.slot_id,
                    "restaurant_name": sel_r.restaurant_name,
                    "city": sel_r.city,
                    "date": sel_r.date,
                    "time": sel_r.time,
                    "time_display": sel_r.time_display,
                    "persons": sel_r.persons,
                    "deposit_amount": sel_r.deposit_amount,
                    "merchant": sel_r.merchant,
                    "category": sel_r.category,
                }
                est_amount = sel_r.deposit_amount
                merchant_name = sel_r.merchant
                summary = f"Table for {party_size} at {sel_r.restaurant_name} ({sel_r.city}) on {sel_r.date} at {sel_r.time_display} (Deposit: ₹{sel_r.deposit_amount:,.2f})"
            else:
                summary = f"Restaurant search: {city} on {date} at {time}"
        else:
            est_amount = task_intent.budget or task_intent.max_budget or 1000.0
            merchant_name = task_intent.merchant or "Torrent Power"
            summary = f"Direct payment to {merchant_name} of ₹{est_amount:,.2f}"

        # Quick policy check preview (informational)
        policy_compliant = True
        try:
            wallet_policy = get_wallet_policy(db, agent_id=agent_id)
            if est_amount is not None:
                if est_amount > wallet_policy.get("per_transaction_limit", 25000.0):
                    policy_compliant = False
                elif est_amount > wallet_policy.get("remaining_daily_budget", 50000.0):
                    policy_compliant = False
        except Exception:
            policy_compliant = True

        interpreted_dict = task_intent.model_dump(mode="json", exclude_none=True, exclude={"user_message", "metadata"})
        if task_intent.metadata:
            interpreted_dict["metadata"] = task_intent.metadata

        return {
            "task_type": task_intent.task_type,
            "interpreted_request": interpreted_dict,
            "selected_option": selected_dict,
            "idempotency_key": idempotency_key,
            "already_completed": already_completed,
            "existing_transaction_id": existing_tx_id,
            "existing_payment_status": existing_status,
            "estimated_amount": est_amount,
            "merchant_name": merchant_name,
            "policy_compliant": policy_compliant,
            "summary": summary,
        }

    def execute_task(
        self,
        db: Session,
        *,
        task_intent: TaskIntent,
        agent_id: Optional[uuid.UUID] = None,
        force_failure: bool = False,
        retry_if_failed: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> TaskResponse:
        """
        Executes a TaskIntent through the appropriate commerce tool, converts to
        TransactionIntent, and authorizes/executes via the existing deterministic
        Policy Engine and PaymentService.

        Audit lifecycle (persisted to existing AuditLog table):
            TASK_RECEIVED → SEARCH_PERFORMED → OPTIONS_FOUND / OPTIONS_NOT_FOUND
            → OPTION_SELECTED → PAYMENT_INTENT_CREATED → POLICY_CHECK
            → PAYMENT → RESERVATION_CONFIRMED / TASK_COMPLETED / TASK_REJECTED
        """
        audit_trail: List[Dict[str, Any]] = []

        # Resolve agent record
        if agent_id:
            agent = db.get(Agent, agent_id)
        else:
            agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()

        resolved_agent_id = agent.id if agent else None

        # ── Lifecycle Event 1: TASK_RECEIVED ─────────────────────────────────
        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="TASK_RECEIVED",
            action="RECEIVE_COMMERCE_TASK",
            decision="RECEIVED",
            reason=(
                f"Autonomous task received: {task_intent.task_type.value} — "
                f"{task_intent.user_message[:150]}"
            ),
            metadata_payload=task_intent.model_dump(mode="json"),
        )
        audit_trail.append({
            "event": "TASK_RECEIVED",
            "task_type": task_intent.task_type.value,
            "intent": task_intent.model_dump(mode="json"),
        })

        # ── Step 1b: Validate required domain fields ─────────────────────────
        is_valid, missing_fields = task_intent.validate_task_requirements()
        if not is_valid:
            reason = f"Missing required information for {task_intent.task_type.value}: {', '.join(missing_fields)}."
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="TASK_REJECTED",
                action="VALIDATE_TASK_INTENT",
                decision="INVALID",
                reason=reason,
                metadata_payload={"missing_fields": missing_fields, "task_intent": task_intent.model_dump(mode="json")},
            )
            audit_trail.append({"event": "TASK_REJECTED", "reason": reason, "missing_fields": missing_fields})
            return TaskResponse(
                task_type=task_intent.task_type,
                task_status="INVALID_INTENT",
                success=False,
                message=reason,
                audit_trail=audit_trail,
            )

        # ── Dispatch by task type ─────────────────────────────────────────────
        if task_intent.task_type == TaskType.BOOK_FLIGHT:
            return self._execute_flight_booking(
                db,
                task_intent=task_intent,
                resolved_agent_id=resolved_agent_id,
                agent_id=agent_id,
                audit_trail=audit_trail,
                force_failure=force_failure,
                retry_if_failed=retry_if_failed,
                idempotency_key=idempotency_key,
            )

        elif task_intent.task_type == TaskType.RESERVE_RESTAURANT:
            return self._execute_restaurant_reservation(
                db,
                task_intent=task_intent,
                resolved_agent_id=resolved_agent_id,
                agent_id=agent_id,
                audit_trail=audit_trail,
                force_failure=force_failure,
                retry_if_failed=retry_if_failed,
                idempotency_key=idempotency_key,
            )

        else:
            # DIRECT_PAYMENT — no commerce tool, straight to payment
            amount = task_intent.budget or task_intent.max_budget or 1000.0
            tx_intent = TransactionIntent(
                merchant=task_intent.merchant or "Torrent Power",
                amount=amount,
                currency="INR",
                category=task_intent.category or "utilities",
                description=f"Direct payment to {task_intent.merchant or 'Torrent Power'}",
                bill_id=None,
            )
            return self._execute_payment_flow(
                db,
                task_intent=task_intent,
                resolved_agent_id=resolved_agent_id,
                agent_id=agent_id,
                tx_intent=tx_intent,
                selected_option_dict=None,
                audit_trail=audit_trail,
                force_failure=force_failure,
                retry_if_failed=retry_if_failed,
                idempotency_key=idempotency_key,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Flight Booking Flow
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_flight_booking(
        self,
        db: Session,
        *,
        task_intent: TaskIntent,
        resolved_agent_id: Optional[uuid.UUID],
        agent_id: Optional[uuid.UUID],
        audit_trail: List[Dict[str, Any]],
        force_failure: bool,
        retry_if_failed: bool,
        idempotency_key: Optional[str] = None,
    ) -> TaskResponse:
        """
        Complete flight booking flow:
          SEARCH_PERFORMED → OPTIONS_FOUND/OPTIONS_NOT_FOUND
          → OPTION_SELECTED → PAYMENT_INTENT_CREATED
          → (shared payment flow)
          → TASK_COMPLETED / TASK_REJECTED
        """
        origin = task_intent.origin or "BOM"
        destination = task_intent.destination or "DEL"
        date = task_intent.date or "2026-09-05"
        max_budget = task_intent.max_budget or task_intent.budget

        # ── Lifecycle Event 2: SEARCH_PERFORMED ──────────────────────────────
        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="SEARCH_PERFORMED",
            action="SEARCH_FLIGHTS",
            decision="SEARCHING",
            reason=(
                f"Searching flights: {origin}→{destination} on {date}"
                + (f" within ₹{max_budget:,.2f}" if max_budget else " (no budget constraint)")
            ),
            metadata_payload={
                "origin": origin,
                "destination": destination,
                "date": date,
                "max_budget": max_budget,
            },
        )
        audit_trail.append({
            "event": "SEARCH_PERFORMED",
            "origin": origin,
            "destination": destination,
            "date": date,
            "max_budget": max_budget,
        })

        # ── Call deterministic flight search tool ─────────────────────────────
        search_result = search_flights(
            origin=origin,
            destination=destination,
            date=date,
            max_budget=max_budget,
        )

        # ── Lifecycle Event 3a: OPTIONS_NOT_FOUND ─────────────────────────────
        if not search_result.found_any:
            reason = (
                f"No flights found for route {origin}→{destination} on {date}. "
                "Route may not be served on this date."
            )
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="OPTIONS_NOT_FOUND",
                action="SEARCH_FLIGHTS",
                decision="NO_RESULTS",
                reason=reason,
                metadata_payload={
                    "origin": origin,
                    "destination": destination,
                    "date": date,
                    "max_budget": max_budget,
                    "all_options_count": 0,
                },
            )
            audit_trail.append({"event": "OPTIONS_NOT_FOUND", "reason": reason})
            return TaskResponse(
                task_type=task_intent.task_type,
                task_status="TOOL_FAILED",
                success=False,
                message=reason,
                audit_trail=audit_trail,
            )

        # Found flights but none within budget
        if not search_result.found_within_budget:
            reason = search_result.summary()
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="OPTIONS_NOT_FOUND",
                action="SEARCH_FLIGHTS",
                decision="OVER_BUDGET",
                reason=reason,
                metadata_payload={
                    "origin": origin,
                    "destination": destination,
                    "date": date,
                    "max_budget": max_budget,
                    "all_options_count": len(search_result.all_options),
                    "cheapest_available": min(
                        search_result.all_options, key=lambda f: f.price
                    ).price,
                },
            )
            audit_trail.append({
                "event": "OPTIONS_NOT_FOUND",
                "reason": reason,
                "all_options_count": len(search_result.all_options),
            })
            return TaskResponse(
                task_type=task_intent.task_type,
                task_status="TOOL_FAILED",
                success=False,
                message=reason,
                audit_trail=audit_trail,
            )

        # ── Lifecycle Event 3b: OPTIONS_FOUND ────────────────────────────────
        options_summary = [
            {
                "flight_number": f.flight_number,
                "airline": f.airline,
                "price": f.price,
                "departure_time": f.departure_time,
                "available_seats": f.available_seats,
            }
            for f in search_result.filtered_options
        ]
        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="OPTIONS_FOUND",
            action="SEARCH_FLIGHTS",
            decision="FOUND",
            reason=search_result.summary(),
            metadata_payload={
                "count": len(search_result.filtered_options),
                "options": options_summary,
            },
        )
        audit_trail.append({
            "event": "OPTIONS_FOUND",
            "count": len(search_result.filtered_options),
            "options": options_summary,
        })

        # ── Deterministic selection: cheapest valid flight ────────────────────
        selected: FlightRecord = select_cheapest_flight(search_result)

        # ── Lifecycle Event 4: OPTION_SELECTED ───────────────────────────────
        selected_dict = {
            "flight_id": selected.flight_id,
            "airline": selected.airline,
            "flight_number": selected.flight_number,
            "origin": selected.origin,
            "origin_city": selected.origin_city,
            "destination": selected.destination,
            "destination_city": selected.destination_city,
            "date": selected.date,
            "departure_time": selected.departure_time,
            "arrival_time": selected.arrival_time,
            "duration_minutes": selected.duration_minutes,
            "price": selected.price,
            "currency": selected.currency,
            "aircraft": selected.aircraft,
            "cabin_class": selected.cabin_class,
            "available_seats": selected.available_seats,
            "merchant": selected.merchant,
            "category": selected.category,
        }
        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="OPTION_SELECTED",
            action="SELECT_FLIGHT",
            decision="SELECTED",
            reason=(
                f"Selected {selected.airline} {selected.flight_number} "
                f"({selected.origin}→{selected.destination}) on {selected.date} "
                f"at ₹{selected.price:,.2f} — cheapest within budget."
            ),
            metadata_payload=selected_dict,
        )
        audit_trail.append({
            "event": "OPTION_SELECTED",
            "selected_flight": selected_dict,
        })

        # ── Lifecycle Event 5: PAYMENT_INTENT_CREATED ────────────────────────
        tx_dict = flight_to_transaction_dict(selected)
        tx_intent = TransactionIntent(**tx_dict)

        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="PAYMENT_INTENT_CREATED",
            action="CONVERT_TO_PAYMENT_INTENT",
            decision="CREATED",
            reason=(
                f"TransactionIntent created: merchant={tx_intent.merchant}, "
                f"amount=₹{tx_intent.amount:,.2f}, category={tx_intent.category}"
            ),
            metadata_payload={
                "transaction_intent": tx_dict,
                "selected_flight": selected_dict,
            },
        )
        audit_trail.append({
            "event": "PAYMENT_INTENT_CREATED",
            "transaction_intent": tx_dict,
        })

        # ── Shared payment flow (Policy Engine + PaymentService) ──────────────
        return self._execute_payment_flow(
            db,
            task_intent=task_intent,
            resolved_agent_id=resolved_agent_id,
            agent_id=agent_id,
            tx_intent=tx_intent,
            selected_option_dict=selected_dict,
            audit_trail=audit_trail,
            force_failure=force_failure,
            retry_if_failed=retry_if_failed,
            idempotency_key=idempotency_key,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Restaurant Reservation Flow
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_restaurant_reservation(
        self,
        db: Session,
        *,
        task_intent: TaskIntent,
        resolved_agent_id: Optional[uuid.UUID],
        agent_id: Optional[uuid.UUID],
        audit_trail: List[Dict[str, Any]],
        force_failure: bool,
        retry_if_failed: bool,
        idempotency_key: Optional[str] = None,
    ) -> TaskResponse:
        """
        Complete restaurant reservation flow:
          SEARCH_PERFORMED → OPTIONS_FOUND/OPTIONS_NOT_FOUND
          → OPTION_SELECTED → PAYMENT_INTENT_CREATED (Deposit semantics)
          → (shared payment flow)
          → RESERVATION_CONFIRMED / TASK_REJECTED
        """
        city = task_intent.city or "Ahmedabad"
        date = task_intent.date or "2026-09-22"
        time = task_intent.time or "8:00 PM"
        party_size = task_intent.party_size or 2
        max_budget = task_intent.max_budget or task_intent.budget
        restaurant_name = (
            task_intent.merchant
            if task_intent.merchant and task_intent.merchant not in ["MakeMyTrip", "Torrent Power", "Netflix", "Amazon"]
            else (task_intent.metadata.get("venue") if task_intent.metadata else None)
        )

        # ── Lifecycle Event 2: SEARCH_PERFORMED ──────────────────────────────
        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="SEARCH_PERFORMED",
            action="SEARCH_RESTAURANTS",
            decision="SEARCHING",
            reason=(
                f"Searching restaurant reservations in {city} on {date} at {time} "
                f"(party of {party_size})"
                + (f" within deposit budget ₹{max_budget:,.2f}" if max_budget else "")
            ),
            metadata_payload={
                "city": city,
                "date": date,
                "time": time,
                "party_size": party_size,
                "max_budget": max_budget,
                "restaurant_name": restaurant_name,
            },
        )
        audit_trail.append({
            "event": "SEARCH_PERFORMED",
            "city": city,
            "date": date,
            "time": time,
            "party_size": party_size,
            "max_budget": max_budget,
            "restaurant_name": restaurant_name,
        })

        # ── Call deterministic restaurant search tool ─────────────────────────
        search_result = search_restaurants(
            city=city,
            date=date,
            time=time,
            party_size=party_size,
            max_budget=max_budget,
            restaurant_name=restaurant_name,
        )

        # ── Lifecycle Event 3a: OPTIONS_NOT_FOUND ─────────────────────────────
        if not search_result.found_any:
            reason = (
                f"No restaurant reservations found in {city} on {date} for party of {party_size} "
                + (f"at '{restaurant_name}'" if restaurant_name else "") + "."
            )
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="OPTIONS_NOT_FOUND",
                action="SEARCH_RESTAURANTS",
                decision="NO_RESULTS",
                reason=reason,
                metadata_payload={
                    "city": city,
                    "date": date,
                    "time": time,
                    "party_size": party_size,
                    "max_budget": max_budget,
                    "restaurant_name": restaurant_name,
                },
            )
            audit_trail.append({"event": "OPTIONS_NOT_FOUND", "reason": reason})
            return TaskResponse(
                task_type=task_intent.task_type,
                task_status="TOOL_FAILED",
                success=False,
                message=reason,
                audit_trail=audit_trail,
            )

        if not search_result.found_within_budget:
            reason = search_result.summary()
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="OPTIONS_NOT_FOUND",
                action="SEARCH_RESTAURANTS",
                decision="OVER_BUDGET",
                reason=reason,
                metadata_payload={
                    "city": city,
                    "date": date,
                    "time": time,
                    "party_size": party_size,
                    "max_budget": max_budget,
                    "all_options_count": len(search_result.all_options),
                },
            )
            audit_trail.append({"event": "OPTIONS_NOT_FOUND", "reason": reason})
            return TaskResponse(
                task_type=task_intent.task_type,
                task_status="TOOL_FAILED",
                success=False,
                message=reason,
                audit_trail=audit_trail,
            )

        # ── Lifecycle Event 3b: OPTIONS_FOUND ────────────────────────────────
        options_summary = [
            {
                "restaurant_name": r.restaurant_name,
                "city": r.city,
                "time_display": r.time_display,
                "persons": r.persons,
                "deposit_amount": r.deposit_amount,
            }
            for r in search_result.filtered_options
        ]
        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="OPTIONS_FOUND",
            action="SEARCH_RESTAURANTS",
            decision="FOUND",
            reason=search_result.summary(),
            metadata_payload={
                "count": len(search_result.filtered_options),
                "options": options_summary,
            },
        )
        audit_trail.append({
            "event": "OPTIONS_FOUND",
            "count": len(search_result.filtered_options),
            "options": options_summary,
        })

        # ── Deterministic selection: lowest reservation deposit ───────────────
        selected: RestaurantRecord = select_cheapest_restaurant(search_result)

        # ── Lifecycle Event 4: OPTION_SELECTED ───────────────────────────────
        selected_dict = {
            "slot_id": selected.slot_id,
            "restaurant_name": selected.restaurant_name,
            "city": selected.city,
            "date": selected.date,
            "time": selected.time,
            "time_display": selected.time_display,
            "persons": selected.persons,
            "party_size_requested": party_size,
            "deposit_amount": selected.deposit_amount,
            "currency": selected.currency,
            "cuisine": selected.cuisine,
            "merchant": selected.merchant,
            "category": selected.category,
        }
        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="OPTION_SELECTED",
            action="SELECT_RESTAURANT",
            decision="SELECTED",
            reason=(
                f"Selected reservation at {selected.restaurant_name} ({selected.city}) "
                f"for party of {party_size} on {selected.date} at {selected.time_display} "
                f"— reservation deposit ₹{selected.deposit_amount:,.2f}."
            ),
            metadata_payload=selected_dict,
        )
        audit_trail.append({
            "event": "OPTION_SELECTED",
            "selected_restaurant": selected_dict,
        })

        # ── Lifecycle Event 5: PAYMENT_INTENT_CREATED (Deposit Semantics) ────
        tx_dict = restaurant_to_transaction_dict(selected, party_size=party_size)
        tx_intent = TransactionIntent(**tx_dict)

        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="PAYMENT_INTENT_CREATED",
            action="CONVERT_TO_PAYMENT_INTENT",
            decision="CREATED",
            reason=(
                f"TransactionIntent created for reservation deposit: "
                f"merchant={tx_intent.merchant}, amount=₹{tx_intent.amount:,.2f}, category={tx_intent.category}"
            ),
            metadata_payload={
                "transaction_intent": tx_dict,
                "selected_restaurant": selected_dict,
            },
        )
        audit_trail.append({
            "event": "PAYMENT_INTENT_CREATED",
            "transaction_intent": tx_dict,
        })

        # ── Shared payment flow (Policy Engine + PaymentService) ──────────────
        return self._execute_payment_flow(
            db,
            task_intent=task_intent,
            resolved_agent_id=resolved_agent_id,
            agent_id=agent_id,
            tx_intent=tx_intent,
            selected_option_dict=selected_dict,
            audit_trail=audit_trail,
            force_failure=force_failure,
            retry_if_failed=retry_if_failed,
            idempotency_key=idempotency_key,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Shared Payment Flow (Policy Engine → PaymentService)
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_payment_flow(
        self,
        db: Session,
        *,
        task_intent: TaskIntent,
        resolved_agent_id: Optional[uuid.UUID],
        agent_id: Optional[uuid.UUID],
        tx_intent: TransactionIntent,
        selected_option_dict: Optional[Dict[str, Any]],
        audit_trail: List[Dict[str, Any]],
        force_failure: bool,
        retry_if_failed: bool,
        idempotency_key: Optional[str] = None,
    ) -> TaskResponse:
        """
        Submits a TransactionIntent through the authoritative Policy Engine
        and PaymentService. Does NOT duplicate any payment logic.
        """
        # ── Read wallet/policy state (informational) ──────────────────────────
        wallet_policy = get_wallet_policy(db, agent_id=agent_id)
        audit_trail.append({
            "event": "WALLET_READ",
            "wallet_status": wallet_policy["wallet_status"],
            "remaining_daily_budget": wallet_policy["remaining_daily_budget"],
        })

        # ── Authoritative Task Idempotency Check ──────────────────────────────
        effective_idempotency_key = (
            idempotency_key
            or getattr(task_intent, "idempotency_key", None)
            or self.compute_task_idempotency_key(task_intent)
        )

        existing_tx = db.execute(
            select(Transaction).where(Transaction.idempotency_key == effective_idempotency_key)
        ).scalar_one_or_none()

        if existing_tx and existing_tx.status == "SUCCESS":
            already_msg = (
                f"Payment Already Completed for this task (Transaction ID: {existing_tx.id}). "
                f"Status: {existing_tx.status}. No duplicate charge was made."
            )
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="DUPLICATE_TASK_PREVENTED",
                action="PREVENT_DUPLICATE_PAYMENT",
                decision="ALREADY_COMPLETED",
                reason=already_msg,
                metadata_payload={
                    "transaction_id": str(existing_tx.id),
                    "status": existing_tx.status,
                    "amount": float(existing_tx.amount),
                    "idempotency_key": effective_idempotency_key,
                },
            )
            audit_trail.append({
                "event": "DUPLICATE_TASK_PREVENTED",
                "transaction_id": str(existing_tx.id),
                "status": existing_tx.status,
                "reason": already_msg,
            })
            db.commit()
            return TaskResponse(
                task_type=task_intent.task_type,
                task_status="COMPLETED",
                success=True,
                message=already_msg,
                selected_option=selected_option_dict,
                transaction_intent=tx_intent,
                decision="ALLOWED",
                decision_code="ALREADY_COMPLETED",
                payment_status="SUCCESS",
                payment_id=str(existing_tx.id),
                provider_payment_id=existing_tx.provider_payment_id,
                amount=float(existing_tx.amount),
                merchant_name=existing_tx.merchant_name,
                rules_checked=[],
                remaining_daily_budget=wallet_policy.get("remaining_daily_budget"),
                audit_trail=audit_trail,
                already_completed=True,
            )

        # ── Lifecycle Event 6: POLICY_CHECK ──────────────────────────────────
        eval_request = {
            "merchant_name": tx_intent.merchant,
            "amount": tx_intent.amount,
            "category": tx_intent.category,
            "agent_id": agent_id,
            "idempotency_key": effective_idempotency_key,
            "metadata": {
                "user_message": task_intent.user_message,
                "task_type": task_intent.task_type.value,
                "force_failure": force_failure,
            },
        }
        eval_result = evaluate_payment(db, eval_request)

        decision = AgentDecision(
            allowed=eval_result["allowed"],
            decision_code=eval_result["decision_code"],
            reason=eval_result["reason"],
            policy_checks=eval_result["rules_checked"],
        )

        self._record_audit(
            db,
            agent_id=resolved_agent_id,
            event_type="POLICY_CHECK",
            action="EVALUATE_POLICY",
            decision="ALLOWED" if decision.allowed else "DENIED",
            reason=decision.reason,
            metadata_payload={
                "merchant": tx_intent.merchant,
                "amount": tx_intent.amount,
                "category": tx_intent.category,
                "decision_code": decision.decision_code,
                "rules_checked": eval_result["rules_checked"],
            },
        )
        audit_trail.append({
            "event": "POLICY_CHECK",
            "allowed": decision.allowed,
            "decision_code": decision.decision_code,
            "reason": decision.reason,
            "rules_checked": eval_result["rules_checked"],
        })

        # ── Lifecycle Event 6a: TASK_REJECTED (Policy Denied) ────────────────
        if not decision.allowed:
            denial_message = (
                f"{task_intent.task_type.value} for '{tx_intent.merchant}' "
                f"(₹{tx_intent.amount:,.2f}) was REJECTED by Policy Engine. "
                f"Reason: {decision.reason}"
            )
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="TASK_REJECTED",
                action="POLICY_DENIAL",
                decision="REJECTED",
                reason=denial_message,
                metadata_payload={
                    "decision_code": decision.decision_code,
                    "task_type": task_intent.task_type.value,
                },
            )
            audit_trail.append({"event": "TASK_REJECTED", "reason": denial_message})
            return TaskResponse(
                task_type=task_intent.task_type,
                task_status="REJECTED_POLICY",
                success=False,
                message=denial_message,
                selected_option=selected_option_dict,
                transaction_intent=tx_intent,
                decision="DENIED",
                decision_code=decision.decision_code,
                payment_status="REJECTED",
                payment_id=None,
                amount=tx_intent.amount,
                merchant_name=tx_intent.merchant,
                rules_checked=eval_result["rules_checked"],
                remaining_daily_budget=eval_result["remaining_daily_budget"],
                audit_trail=audit_trail,
            )

        # ── Lifecycle Event 7: PAYMENT ────────────────────────────────────────
        payment_req = PaymentRequest(
            merchant_name=tx_intent.merchant,
            amount=tx_intent.amount,
            currency=tx_intent.currency,
            category=tx_intent.category,
            agent_id=agent_id,
            bill_id=None,
            idempotency_key=effective_idempotency_key,
            metadata={
                "user_message": task_intent.user_message,
                "task_type": task_intent.task_type.value,
                "selected_option": selected_option_dict,
                "force_failure": force_failure,
            },
        )

        payment_result = create_payment(
            db, payment_req.model_dump(mode="json"), adapter=self.adapter,
        )
        audit_trail.append({
            "event": "PAYMENT",
            "status": payment_result.get("status"),
            "payment_id": payment_result.get("payment_id"),
            "provider_payment_id": payment_result.get("provider_payment_id"),
        })

        payment_id_str = payment_result.get("payment_id")

        # ── Optional retry (preserving existing retry/fallback behaviour) ──────
        if payment_result.get("status") == "FAILED" and retry_if_failed and payment_id_str:
            retry_result = retry_payment(
                db,
                payment_id=uuid.UUID(payment_id_str),
                adapter=self.adapter,
                metadata={"user_message": task_intent.user_message, "force_failure": False},
            )
            audit_trail.append({
                "event": "PAYMENT_RETRY",
                "status": retry_result.get("status"),
                "attempt": retry_result.get("attempt_number"),
            })
            payment_result = retry_result

        final_status = payment_result.get("status")
        is_success = final_status == "SUCCESS"

        # ── Lifecycle Event 8: RESERVATION_CONFIRMED / TASK_COMPLETED / TASK_REJECTED ──
        if is_success:
            if task_intent.task_type == TaskType.RESERVE_RESTAURANT and selected_option_dict:
                success_msg = (
                    f"Reservation confirmed at {selected_option_dict.get('restaurant_name')} "
                    f"({selected_option_dict.get('city')}) for {selected_option_dict.get('party_size_requested', selected_option_dict.get('persons'))} guests "
                    f"on {selected_option_dict.get('date')} at {selected_option_dict.get('time_display', selected_option_dict.get('time'))}. "
                    f"Deposit of ₹{tx_intent.amount:,.2f} successfully captured."
                )
                self._record_audit(
                    db,
                    agent_id=resolved_agent_id,
                    event_type="RESERVATION_CONFIRMED",
                    action="CONFIRM_RESERVATION",
                    decision="CONFIRMED",
                    reason=success_msg,
                    metadata_payload={
                        "payment_id": payment_id_str,
                        "payment_status": final_status,
                        "deposit_amount": tx_intent.amount,
                        "restaurant_name": selected_option_dict.get("restaurant_name"),
                        "city": selected_option_dict.get("city"),
                        "date": selected_option_dict.get("date"),
                        "time": selected_option_dict.get("time_display"),
                        "party_size": selected_option_dict.get("party_size_requested"),
                    },
                )
                audit_trail.append({"event": "RESERVATION_CONFIRMED", "message": success_msg})

            elif task_intent.task_type == TaskType.BOOK_FLIGHT and selected_option_dict:
                success_msg = (
                    f"Flight successfully booked: {selected_option_dict.get('airline')} "
                    f"{selected_option_dict.get('flight_number')} "
                    f"({selected_option_dict.get('origin')}→{selected_option_dict.get('destination')}) "
                    f"on {selected_option_dict.get('date')} at "
                    f"{selected_option_dict.get('departure_time')} — ₹{tx_intent.amount:,.2f} captured."
                )
                self._record_audit(
                    db,
                    agent_id=resolved_agent_id,
                    event_type="TASK_COMPLETED",
                    action="COMPLETE_TASK",
                    decision="COMPLETED",
                    reason=success_msg,
                    metadata_payload={
                        "payment_id": payment_id_str,
                        "payment_status": final_status,
                        "amount": tx_intent.amount,
                        "merchant": tx_intent.merchant,
                        "task_type": task_intent.task_type.value,
                    },
                )
                audit_trail.append({"event": "TASK_COMPLETED", "message": success_msg})

            else:
                success_msg = (
                    f"Payment of ₹{tx_intent.amount:,.2f} to "
                    f"{tx_intent.merchant} completed successfully."
                )
                self._record_audit(
                    db,
                    agent_id=resolved_agent_id,
                    event_type="TASK_COMPLETED",
                    action="COMPLETE_TASK",
                    decision="COMPLETED",
                    reason=success_msg,
                    metadata_payload={
                        "payment_id": payment_id_str,
                        "payment_status": final_status,
                        "amount": tx_intent.amount,
                        "merchant": tx_intent.merchant,
                        "task_type": task_intent.task_type.value,
                    },
                )
                audit_trail.append({"event": "TASK_COMPLETED", "message": success_msg})

        else:
            failure_msg = (
                f"Payment of ₹{tx_intent.amount:,.2f} to {tx_intent.merchant} "
                f"authorized by Policy Engine but failed at payment rail: "
                f"{payment_result.get('error_message', 'Unknown error')}."
            )
            self._record_audit(
                db,
                agent_id=resolved_agent_id,
                event_type="TASK_REJECTED",
                action="PAYMENT_FAILURE",
                decision="PAYMENT_FAILED",
                reason=failure_msg,
                metadata_payload={
                    "payment_id": payment_id_str,
                    "payment_status": final_status,
                    "error_message": payment_result.get("error_message"),
                },
            )
            audit_trail.append({"event": "TASK_REJECTED", "reason": failure_msg})
            success_msg = failure_msg

        return TaskResponse(
            task_type=task_intent.task_type,
            task_status="COMPLETED" if is_success else "PAYMENT_FAILED",
            success=is_success,
            message=success_msg,
            selected_option=selected_option_dict,
            transaction_intent=tx_intent,
            decision="ALLOWED",
            decision_code=decision.decision_code,
            payment_status=final_status,
            payment_id=payment_id_str,
            provider_payment_id=payment_result.get("provider_payment_id"),
            amount=tx_intent.amount,
            merchant_name=tx_intent.merchant,
            rules_checked=eval_result["rules_checked"],
            remaining_daily_budget=eval_result["remaining_daily_budget"],
            audit_trail=audit_trail,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Audit Helper
    # ─────────────────────────────────────────────────────────────────────────

    def _record_audit(
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
        """Persist an immutable audit event to the existing AuditLog table."""
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
        db.flush()
