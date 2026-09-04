"""
Deterministic Restaurant Reservation Search Tool for AgentPay.

Provides structured, mock restaurant inventory for autonomous reservation demos.
This tool is 100% deterministic — venue names, dates, times, party sizes,
availability, and reservation deposits are hard-coded and cannot be fabricated by an LLM.

PAYMENT SEMANTICS:
- AgentPay pays a RESERVATION DEPOSIT to secure the booking, NOT the entire meal bill.
- Deposit transactions pass through the existing authoritative Policy Engine and PaymentService.

SECURITY INVARIANTS:
- This tool only SEARCHES and SELECTS. It never processes payments.
- It never calls real restaurant reservation APIs.
- Reservation confirmation is only granted after payment succeeds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class RestaurantRecord:
    """An immutable deterministic restaurant reservation slot from mock inventory."""
    slot_id: str
    restaurant_name: str
    city: str
    date: str                # ISO format: YYYY-MM-DD
    time: str                # 24-hr format (e.g. "20:00")
    time_display: str        # e.g. "8:00 PM"
    persons: int             # Table capacity (party size supported)
    reservation_available: bool
    deposit_amount: float    # Reservation deposit in INR
    currency: str = "INR"
    cuisine: str = "Multi-Cuisine"
    merchant: str = "Restaurant"
    category: str = "dining"


@dataclass
class RestaurantSearchResult:
    """Structured result from a restaurant reservation search operation."""
    search_city: str
    search_date: str
    search_time: Optional[str]
    search_party_size: int
    search_restaurant_name: Optional[str]
    max_budget: Optional[float]
    all_options: List[RestaurantRecord] = field(default_factory=list)
    filtered_options: List[RestaurantRecord] = field(default_factory=list)

    @property
    def found_any(self) -> bool:
        return len(self.all_options) > 0

    @property
    def found_within_budget(self) -> bool:
        return len(self.filtered_options) > 0

    def summary(self) -> str:
        if not self.found_any:
            target = f"'{self.search_restaurant_name}' in " if self.search_restaurant_name else ""
            return (
                f"No restaurant reservations available for {target}{self.search_city} "
                f"on {self.search_date} (party of {self.search_party_size})."
            )
        if not self.found_within_budget:
            cheapest = min(self.all_options, key=lambda r: r.deposit_amount)
            budget_str = f"₹{self.max_budget:,.2f}" if self.max_budget is not None else "specified budget"
            return (
                f"Found {len(self.all_options)} reservation option(s) in {self.search_city} "
                f"on {self.search_date}, but none within deposit budget {budget_str}. "
                f"Lowest deposit available: ₹{cheapest.deposit_amount:,.2f} at {cheapest.restaurant_name}."
            )
        budget_clause = f" within deposit budget ₹{self.max_budget:,.2f}" if self.max_budget is not None else ""
        return (
            f"Found {len(self.filtered_options)} reservation option(s){budget_clause} in "
            f"{self.search_city} on {self.search_date} (party of {self.search_party_size})."
        )


def _normalize_time(time_str: Optional[str]) -> Optional[str]:
    """Normalize time string like '8 PM', '8:00 PM', '20:00' to '20:00'."""
    if not time_str:
        return None
    t = time_str.strip().lower()
    # Check 12-hour format e.g. 8 pm, 8:30 pm, 8:00 pm
    match_12 = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$', t)
    if match_12:
        hour = int(match_12.group(1))
        minute = int(match_12.group(2) or 0)
        ampm = match_12.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    # Check 24-hour format e.g. 20:00, 20:30
    match_24 = re.match(r'^(\d{1,2}):(\d{2})$', t)
    if match_24:
        return f"{int(match_24.group(1)):02d}:{int(match_24.group(2)):02d}"
    return None


# ---------------------------------------------------------------------------
# Deterministic Mock Restaurant Inventory
# ---------------------------------------------------------------------------

_MOCK_RESTAURANT_INVENTORY: List[RestaurantRecord] = [
    # ─── Ahmedabad | September 22, 2026 ──────────────────────────────────
    RestaurantRecord(
        slot_id="slot_itc_narmada_20260922_2000",
        restaurant_name="ITC Narmada",
        city="Ahmedabad",
        date="2026-09-22",
        time="20:00",
        time_display="8:00 PM",
        persons=2,
        reservation_available=True,
        deposit_amount=1000.0,
        currency="INR",
        cuisine="Luxury Fine Dining & Indian",
        merchant="ITC Narmada",
        category="dining",
    ),
    RestaurantRecord(
        slot_id="slot_ks_charcoal_20260922_2030",
        restaurant_name="K's Charcoal",
        city="Ahmedabad",
        date="2026-09-22",
        time="20:30",
        time_display="8:30 PM",
        persons=5,
        reservation_available=True,
        deposit_amount=600.0,
        currency="INR",
        cuisine="Wood-fired Gourmet & Italian",
        merchant="K's Charcoal",
        category="dining",
    ),
    RestaurantRecord(
        slot_id="slot_pepito_20260922_2000",
        restaurant_name="Pepito",
        city="Ahmedabad",
        date="2026-09-22",
        time="20:00",
        time_display="8:00 PM",
        persons=4,
        reservation_available=True,
        deposit_amount=800.0,
        currency="INR",
        cuisine="Contemporary Continental & Mexican",
        merchant="Pepito",
        category="dining",
    ),
    RestaurantRecord(
        slot_id="slot_itc_narmada_20260904_2000",
        restaurant_name="ITC Narmada",
        city="Ahmedabad",
        date="2026-09-04",
        time="20:00",
        time_display="8:00 PM",
        persons=2,
        reservation_available=True,
        deposit_amount=1000.0,
        currency="INR",
        cuisine="Luxury Fine Dining & Indian",
        merchant="ITC Narmada",
        category="dining",
    ),
    # ─── Mumbai | Various ────────────────────────────────────────────────
    RestaurantRecord(
        slot_id="slot_trishna_mumbai_20260904_1930",
        restaurant_name="Trishna",
        city="Mumbai",
        date="2026-09-04",
        time="19:30",
        time_display="7:30 PM",
        persons=2,
        reservation_available=True,
        deposit_amount=1800.0,
        currency="INR",
        cuisine="Coastal & Seafood",
        merchant="Trishna Seafood",
        category="dining",
    ),
    RestaurantRecord(
        slot_id="slot_trishna_mumbai_20260904_2000",
        restaurant_name="Trishna",
        city="Mumbai",
        date="2026-09-04",
        time="20:00",
        time_display="8:00 PM",
        persons=2,
        reservation_available=True,
        deposit_amount=1800.0,
        currency="INR",
        cuisine="Coastal & Seafood",
        merchant="Trishna Seafood",
        category="dining",
    ),
    RestaurantRecord(
        slot_id="slot_trishna_mumbai_20260904_2030",
        restaurant_name="Trishna",
        city="Mumbai",
        date="2026-09-04",
        time="20:30",
        time_display="8:30 PM",
        persons=2,
        reservation_available=True,
        deposit_amount=1800.0,
        currency="INR",
        cuisine="Coastal & Seafood",
        merchant="Trishna Seafood",
        category="dining",
    ),
    RestaurantRecord(
        slot_id="slot_trishna_mumbai_20260922_2030",
        restaurant_name="Trishna",
        city="Mumbai",
        date="2026-09-22",
        time="20:30",
        time_display="8:30 PM",
        persons=2,
        reservation_available=True,
        deposit_amount=1800.0,
        currency="INR",
        cuisine="Coastal & Seafood",
        merchant="Trishna Seafood",
        category="dining",
    ),
    RestaurantRecord(
        slot_id="slot_the_table_mumbai_20260904_2000",
        restaurant_name="The Table",
        city="Mumbai",
        date="2026-09-04",
        time="20:00",
        time_display="8:00 PM",
        persons=4,
        reservation_available=True,
        deposit_amount=2400.0,
        currency="INR",
        cuisine="Global Fine Dining",
        merchant="The Table Colaba",
        category="dining",
    ),
    # ─── Delhi | Various ─────────────────────────────────────────────────
    RestaurantRecord(
        slot_id="slot_bukhara_delhi_20260904_2000",
        restaurant_name="Bukhara",
        city="Delhi",
        date="2026-09-04",
        time="20:00",
        time_display="8:00 PM",
        persons=2,
        reservation_available=True,
        deposit_amount=2500.0,
        currency="INR",
        cuisine="North Western Frontier",
        merchant="Bukhara ITC Maurya",
        category="dining",
    ),
]


# ---------------------------------------------------------------------------
# Public Search & Selection API
# ---------------------------------------------------------------------------

def search_restaurants(
    city: str,
    date: str,
    time: Optional[str] = None,
    party_size: int = 2,
    max_budget: Optional[float] = None,
    restaurant_name: Optional[str] = None,
) -> RestaurantSearchResult:
    """
    Search deterministic restaurant inventory.

    Args:
        city:             City name (e.g. "Ahmedabad", "Mumbai")
        date:             ISO date string (e.g. "2026-09-22")
        time:             Optional time slot string (e.g. "8:00 PM" or "20:00")
        party_size:       Number of guests needing reservation (defaults to 2)
        max_budget:       Maximum acceptable reservation deposit in INR
        restaurant_name:  Optional specific restaurant venue filter
    """
    clean_city = city.strip().lower()
    target_time_24 = _normalize_time(time)

    matches: List[RestaurantRecord] = []
    for r in _MOCK_RESTAURANT_INVENTORY:
        # Match city (case-insensitive)
        if r.city.strip().lower() != clean_city:
            continue
        # Match date
        if r.date != date:
            continue
        # Match party capacity (table capacity >= requested party size)
        if r.persons < party_size:
            continue
        # Match availability
        if not r.reservation_available:
            continue
        # Match specific restaurant name if provided
        if restaurant_name:
            req_name = restaurant_name.strip().lower()
            venue_name = r.restaurant_name.strip().lower()
            if req_name not in venue_name and venue_name not in req_name:
                continue
        # Match time if provided
        if target_time_24 and r.time != target_time_24:
            continue

        matches.append(r)

    # Filter against user maximum deposit budget
    within_budget = (
        [r for r in matches if r.deposit_amount <= max_budget]
        if max_budget is not None
        else list(matches)
    )

    return RestaurantSearchResult(
        search_city=city.strip(),
        search_date=date,
        search_time=time,
        search_party_size=party_size,
        search_restaurant_name=restaurant_name,
        max_budget=max_budget,
        all_options=matches,
        filtered_options=within_budget,
    )


def select_cheapest_restaurant(result: RestaurantSearchResult) -> Optional[RestaurantRecord]:
    """
    Deterministically select the option with the lowest reservation deposit.
    Returns None if no matching reservations exist within budget.
    """
    if not result.filtered_options:
        return None
    return min(result.filtered_options, key=lambda r: r.deposit_amount)


def restaurant_to_transaction_dict(restaurant: RestaurantRecord, party_size: int = 2) -> dict:
    """
    Convert a RestaurantRecord into an authoritative AgentPay TransactionIntent dictionary.
    Semantics: Pays a reservation deposit for the requested party size.
    """
    return {
        "merchant": restaurant.merchant,
        "amount": restaurant.deposit_amount,
        "currency": restaurant.currency,
        "category": restaurant.category,
        "description": (
            f"Restaurant reservation deposit for {party_size} people at "
            f"{restaurant.restaurant_name} ({restaurant.city}) on {restaurant.date} at {restaurant.time_display}"
        ),
        "bill_id": None,
    }
