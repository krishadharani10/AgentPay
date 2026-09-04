"""
Deterministic Flight Search Tool for AgentPay.

Provides a structured, mock flight inventory for autonomous booking demos.
This tool is 100% deterministic — flight data, prices, availability, and
schedules are hard-coded and cannot be fabricated by an LLM.

SECURITY INVARIANTS:
- This tool only SEARCHES and SELECTS. It never processes payments.
- It never calls real airline APIs.
- All flight data is hard-coded for reproducible demo scenarios.
- Flight selection converts to TransactionIntent and then passes
  through the existing authoritative Policy Engine and PaymentService.

Usage:
    results = search_flights("AMD", "BOM", date="2026-09-05", max_budget=10000)
    selected = select_cheapest_flight(results)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Flight data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlightRecord:
    """An immutable deterministic flight record from the mock inventory."""
    flight_id: str
    airline: str
    flight_number: str
    origin: str           # IATA code, e.g. "AMD"
    origin_city: str
    destination: str      # IATA code, e.g. "BOM"
    destination_city: str
    date: str             # ISO format: YYYY-MM-DD
    departure_time: str   # HH:MM
    arrival_time: str     # HH:MM
    duration_minutes: int
    price: float
    currency: str = "INR"
    aircraft: str = "Airbus A320"
    available_seats: int = 40
    cabin_class: str = "Economy"
    # Merchant name used when converting to TransactionIntent
    merchant: str = "AirDemo"
    category: str = "travel"


@dataclass
class FlightSearchResult:
    """Structured result from a flight search operation."""
    search_origin: str
    search_destination: str
    search_date: str
    max_budget: Optional[float]
    all_options: List[FlightRecord] = field(default_factory=list)
    filtered_options: List[FlightRecord] = field(default_factory=list)

    @property
    def found_any(self) -> bool:
        return len(self.all_options) > 0

    @property
    def found_within_budget(self) -> bool:
        return len(self.filtered_options) > 0

    def summary(self) -> str:
        if not self.found_any:
            return (
                f"No flights found for {self.search_origin}→{self.search_destination} "
                f"on {self.search_date}."
            )
        if not self.found_within_budget:
            cheapest = min(self.all_options, key=lambda f: f.price)
            budget_str = f"₹{self.max_budget:,.2f}" if self.max_budget is not None else "specified budget"
            return (
                f"Found {len(self.all_options)} flight(s) for "
                f"{self.search_origin}→{self.search_destination} on {self.search_date}, "
                f"but none within budget {budget_str}. "
                f"Cheapest available: ₹{cheapest.price:,.2f} ({cheapest.airline} {cheapest.flight_number})."
            )
        budget_clause = f" within budget ₹{self.max_budget:,.2f}" if self.max_budget is not None else ""
        return (
            f"Found {len(self.filtered_options)} flight(s){budget_clause} for "
            f"{self.search_origin}→{self.search_destination} on {self.search_date}."
        )


# ---------------------------------------------------------------------------
# IATA city/code normalization map
# ---------------------------------------------------------------------------

_CITY_TO_IATA: dict[str, str] = {
    "ahmedabad": "AMD",
    "amd": "AMD",
    "mumbai": "BOM",
    "bombay": "BOM",
    "bom": "BOM",
    "delhi": "DEL",
    "new delhi": "DEL",
    "del": "DEL",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "blr": "BLR",
    "hyderabad": "HYD",
    "hyd": "HYD",
    "chennai": "MAA",
    "madras": "MAA",
    "maa": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "ccu": "CCU",
    "goa": "GOI",
    "goi": "GOI",
    "pune": "PNQ",
    "pnq": "PNQ",
    "jaipur": "JAI",
    "jai": "JAI",
    "kochi": "COK",
    "cok": "COK",
}

def _normalize_iata(city_or_code: str) -> str:
    """Return uppercase IATA code for a city name or IATA code."""
    key = city_or_code.strip().lower()
    return _CITY_TO_IATA.get(key, city_or_code.strip().upper())


# ---------------------------------------------------------------------------
# Deterministic mock flight inventory
# ---------------------------------------------------------------------------
# AirDemo is a fictional airline used exclusively for AgentPay demos.
# Prices, schedules, and availability are deterministic and reproducible.

_MOCK_INVENTORY: List[FlightRecord] = [
    # ─── AMD → BOM | September 5, 2026 ───────────────────────────────────
    FlightRecord(
        flight_id="airdemo_ap101_amd_bom_20260905",
        airline="AirDemo",
        flight_number="AP101",
        origin="AMD",
        origin_city="Ahmedabad",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-05",
        departure_time="06:15",
        arrival_time="07:30",
        duration_minutes=75,
        price=7450.0,
        available_seats=12,
    ),
    FlightRecord(
        flight_id="airdemo_ap205_amd_bom_20260905",
        airline="AirDemo",
        flight_number="AP205",
        origin="AMD",
        origin_city="Ahmedabad",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-05",
        departure_time="11:45",
        arrival_time="13:05",
        duration_minutes=80,
        price=8250.0,
        available_seats=28,
    ),
    FlightRecord(
        flight_id="airdemo_ap420_amd_bom_20260905",
        airline="AirDemo",
        flight_number="AP420",
        origin="AMD",
        origin_city="Ahmedabad",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-05",
        departure_time="19:30",
        arrival_time="20:55",
        duration_minutes=85,
        price=11500.0,
        available_seats=5,
        cabin_class="Business",
    ),
    # ─── AMD → BOM | September 08, 2026 (Business/Over-limit test date) ───
    FlightRecord(
        flight_id="airdemo_ap420_amd_bom_20260908",
        airline="AirDemo",
        flight_number="AP420",
        origin="AMD",
        origin_city="Ahmedabad",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-08",
        departure_time="19:30",
        arrival_time="20:55",
        duration_minutes=85,
        price=11500.0,
        available_seats=5,
        cabin_class="Business",
    ),
    # ─── AMD → BOM | September 22, 2026 ──────────────────────────────────
    FlightRecord(
        flight_id="airdemo_ap101_amd_bom_20260922",
        airline="AirDemo",
        flight_number="AP101",
        origin="AMD",
        origin_city="Ahmedabad",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-22",
        departure_time="06:15",
        arrival_time="07:30",
        duration_minutes=75,
        price=7450.0,
        available_seats=18,
    ),
    FlightRecord(
        flight_id="airdemo_ap205_amd_bom_20260922",
        airline="AirDemo",
        flight_number="AP205",
        origin="AMD",
        origin_city="Ahmedabad",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-22",
        departure_time="11:45",
        arrival_time="13:05",
        duration_minutes=80,
        price=8250.0,
        available_seats=32,
    ),
    FlightRecord(
        flight_id="airdemo_ap420_amd_bom_20260922",
        airline="AirDemo",
        flight_number="AP420",
        origin="AMD",
        origin_city="Ahmedabad",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-22",
        departure_time="19:30",
        arrival_time="20:55",
        duration_minutes=85,
        price=11500.0,
        available_seats=3,
        cabin_class="Business",
    ),
    # ─── BOM → DEL | Various ──────────────────────────────────────────────
    FlightRecord(
        flight_id="airdemo_ap601_bom_del_20260910",
        airline="AirDemo",
        flight_number="AP601",
        origin="BOM",
        origin_city="Mumbai",
        destination="DEL",
        destination_city="Delhi",
        date="2026-09-10",
        departure_time="07:00",
        arrival_time="09:15",
        duration_minutes=135,
        price=4800.0,
        available_seats=22,
    ),
    FlightRecord(
        flight_id="airdemo_ap602_bom_del_20260910",
        airline="AirDemo",
        flight_number="AP602",
        origin="BOM",
        origin_city="Mumbai",
        destination="DEL",
        destination_city="Delhi",
        date="2026-09-10",
        departure_time="13:30",
        arrival_time="15:50",
        duration_minutes=140,
        price=5950.0,
        available_seats=15,
    ),
    FlightRecord(
        flight_id="airdemo_ap701_bom_del_20260911",
        airline="AirDemo",
        flight_number="AP701",
        origin="BOM",
        origin_city="Mumbai",
        destination="DEL",
        destination_city="Delhi",
        date="2026-09-11",
        departure_time="09:45",
        arrival_time="12:00",
        duration_minutes=135,
        price=3800.0,
        available_seats=30,
    ),
    # ─── DEL → BOM | Various ──────────────────────────────────────────────
    FlightRecord(
        flight_id="airdemo_ap501_del_bom_20260910",
        airline="AirDemo",
        flight_number="AP501",
        origin="DEL",
        origin_city="Delhi",
        destination="BOM",
        destination_city="Mumbai",
        date="2026-09-10",
        departure_time="10:00",
        arrival_time="12:20",
        duration_minutes=140,
        price=4600.0,
        available_seats=20,
    ),
    # ─── BOM → BLR ────────────────────────────────────────────────────────
    FlightRecord(
        flight_id="airdemo_ap301_bom_blr_20260905",
        airline="AirDemo",
        flight_number="AP301",
        origin="BOM",
        origin_city="Mumbai",
        destination="BLR",
        destination_city="Bangalore",
        date="2026-09-05",
        departure_time="08:30",
        arrival_time="10:15",
        duration_minutes=105,
        price=2900.0,
        available_seats=40,
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_flights(
    origin: str,
    destination: str,
    date: str,
    max_budget: Optional[float] = None,
) -> FlightSearchResult:
    """
    Search mock flight inventory for matching routes.

    Args:
        origin:       City name or IATA code (e.g. "Ahmedabad" or "AMD")
        destination:  City name or IATA code (e.g. "Mumbai" or "BOM")
        date:         ISO date string (e.g. "2026-09-05")
        max_budget:   Optional maximum price ceiling in INR

    Returns:
        FlightSearchResult with all_options (pre-budget) and filtered_options (post-budget).
    """
    origin_code = _normalize_iata(origin)
    dest_code = _normalize_iata(destination)

    all_matches: List[FlightRecord] = [
        f for f in _MOCK_INVENTORY
        if f.origin == origin_code
        and f.destination == dest_code
        and f.date == date
    ]

    within_budget: List[FlightRecord] = (
        [f for f in all_matches if f.price <= max_budget]
        if max_budget is not None
        else list(all_matches)
    )

    return FlightSearchResult(
        search_origin=origin_code,
        search_destination=dest_code,
        search_date=date,
        max_budget=max_budget,
        all_options=all_matches,
        filtered_options=within_budget,
    )


def select_cheapest_flight(result: FlightSearchResult) -> Optional[FlightRecord]:
    """
    Deterministically select the cheapest available flight from a search result.
    Returns None if no flights are available within budget.
    """
    if not result.filtered_options:
        return None
    return min(result.filtered_options, key=lambda f: f.price)


def flight_to_transaction_dict(flight: FlightRecord) -> dict:
    """
    Convert a FlightRecord to a dict matching the existing TransactionIntent schema.
    This is the bridge between the flight tool and the authoritative payment core.
    """
    return {
        "merchant": flight.merchant,
        "amount": flight.price,
        "currency": flight.currency,
        "category": flight.category,
        "description": (
            f"Flight {flight.flight_number} {flight.origin}→{flight.destination} "
            f"on {flight.date} ({flight.departure_time}–{flight.arrival_time})"
        ),
        "bill_id": None,
    }
