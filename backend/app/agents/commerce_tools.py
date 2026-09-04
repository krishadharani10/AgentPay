"""
Autonomous Commerce Task Tools for AgentPay.

Implements domain-specific commercial search and selection tools:
1. Flight Booking Tool (`search_flights`, `select_flight`)
2. Restaurant Reservation Tool (`search_restaurants`, `select_restaurant`)

These tools return typed SelectedFlightOption / SelectedRestaurantOption objects
which can be deterministically converted to existing TransactionIntent models.
"""
from typing import Optional, List, Dict, Any
from app.schemas.task_types import SelectedFlightOption, SelectedRestaurantOption


# ─────────────────────────────────────────────────────────────────────────────
# FLIGHT COMMERCE TOOL
# ─────────────────────────────────────────────────────────────────────────────

MOCK_FLIGHT_INVENTORY: List[Dict[str, Any]] = [
    {
        "flight_id": "flt_6e_204_bom_del",
        "airline": "IndiGo",
        "flight_number": "6E-204",
        "origin": "BOM",
        "origin_city": "Mumbai",
        "destination": "DEL",
        "destination_city": "Delhi",
        "departure_time": "06:00",
        "arrival_time": "08:15",
        "price": 4500.0,
        "merchant": "MakeMyTrip",
    },
    {
        "flight_id": "flt_ai_102_bom_del",
        "airline": "Air India",
        "flight_number": "AI-102",
        "origin": "BOM",
        "origin_city": "Mumbai",
        "destination": "DEL",
        "destination_city": "Delhi",
        "departure_time": "09:30",
        "arrival_time": "11:45",
        "price": 6200.0,
        "merchant": "MakeMyTrip",
    },
    {
        "flight_id": "flt_sg_816_bom_del",
        "airline": "SpiceJet",
        "flight_number": "SG-816",
        "origin": "BOM",
        "origin_city": "Mumbai",
        "destination": "DEL",
        "destination_city": "Delhi",
        "departure_time": "18:45",
        "arrival_time": "21:00",
        "price": 3800.0,
        "merchant": "MakeMyTrip",
    },
    {
        "flight_id": "flt_qp_1102_bom_blr",
        "airline": "Akasa Air",
        "flight_number": "QP-1102",
        "origin": "BOM",
        "origin_city": "Mumbai",
        "destination": "BLR",
        "destination_city": "Bangalore",
        "departure_time": "14:30",
        "arrival_time": "16:15",
        "price": 2900.0,
        "merchant": "MakeMyTrip",
    },
    {
        "flight_id": "flt_6e_451_bom_blr",
        "airline": "IndiGo",
        "flight_number": "6E-451",
        "origin": "BOM",
        "origin_city": "Mumbai",
        "destination": "BLR",
        "destination_city": "Bangalore",
        "departure_time": "07:15",
        "arrival_time": "09:00",
        "price": 3500.0,
        "merchant": "MakeMyTrip",
    },
    {
        "flight_id": "flt_6e_344_bom_goi",
        "airline": "IndiGo",
        "flight_number": "6E-344",
        "origin": "BOM",
        "origin_city": "Mumbai",
        "destination": "GOI",
        "destination_city": "Goa",
        "departure_time": "11:00",
        "arrival_time": "12:15",
        "price": 2400.0,
        "merchant": "MakeMyTrip",
    },
    {
        "flight_id": "flt_6e_501_del_bom",
        "airline": "IndiGo",
        "flight_number": "6E-501",
        "origin": "DEL",
        "origin_city": "Delhi",
        "destination": "BOM",
        "destination_city": "Mumbai",
        "departure_time": "08:00",
        "arrival_time": "10:15",
        "price": 4600.0,
        "merchant": "MakeMyTrip",
    },
    {
        "flight_id": "flt_uk_995_del_bom",
        "airline": "Vistara",
        "flight_number": "UK-995",
        "origin": "DEL",
        "origin_city": "Delhi",
        "destination": "BOM",
        "destination_city": "Mumbai",
        "departure_time": "16:30",
        "arrival_time": "18:45",
        "price": 5800.0,
        "merchant": "MakeMyTrip",
    },
]


def _normalize_city_or_code(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val_clean = val.strip().lower()
    city_map = {
        "mumbai": "BOM",
        "bombay": "BOM",
        "bom": "BOM",
        "delhi": "DEL",
        "new delhi": "DEL",
        "del": "DEL",
        "bangalore": "BLR",
        "bengaluru": "BLR",
        "blr": "BLR",
        "goa": "GOI",
        "goi": "GOI",
        "hyderabad": "HYD",
        "hyd": "HYD",
    }
    return city_map.get(val_clean, val.upper())


def search_flights(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    date: Optional[str] = None,
    max_budget: Optional[float] = None,
    preferred_airline: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Searches available flight options matching specified route and budget constraints.
    """
    norm_origin = _normalize_city_or_code(origin)
    norm_dest = _normalize_city_or_code(destination)

    results = []
    for f in MOCK_FLIGHT_INVENTORY:
        if norm_origin and f["origin"] != norm_origin and norm_origin not in f["origin_city"].upper():
            continue
        if norm_dest and f["destination"] != norm_dest and norm_dest not in f["destination_city"].upper():
            continue
        if max_budget is not None and f["price"] > max_budget:
            continue
        if preferred_airline and preferred_airline.lower() not in f["airline"].lower():
            continue

        item = dict(f)
        item["date"] = date or "2026-09-10"
        results.append(item)

    return results


def select_flight(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    date: Optional[str] = None,
    max_budget: Optional[float] = None,
    preferred_airline: Optional[str] = None,
) -> Optional[SelectedFlightOption]:
    """
    Selects the optimal flight option satisfying constraints (e.g. lowest price within budget).
    Returns None if no matching flight is found.
    """
    flights = search_flights(
        origin=origin,
        destination=destination,
        date=date,
        max_budget=max_budget,
        preferred_airline=preferred_airline,
    )
    if not flights:
        return None

    # Sort by price ascending (best value first)
    flights.sort(key=lambda x: x["price"])
    best = flights[0]

    return SelectedFlightOption(
        flight_id=best["flight_id"],
        airline=best["airline"],
        flight_number=best["flight_number"],
        origin=best["origin"],
        destination=best["destination"],
        departure_time=best["departure_time"],
        arrival_time=best["arrival_time"],
        date=best["date"],
        price=float(best["price"]),
        merchant=best.get("merchant", "MakeMyTrip"),
        category="travel",
        currency="INR",
    )


# ─────────────────────────────────────────────────────────────────────────────
# RESTAURANT RESERVATION COMMERCE TOOL
# ─────────────────────────────────────────────────────────────────────────────

MOCK_RESTAURANT_INVENTORY: List[Dict[str, Any]] = [
    {
        "restaurant_id": "rest_trishna_mumbai",
        "restaurant_name": "Trishna",
        "city": "Mumbai",
        "area": "Fort",
        "cuisine": "Coastal & Seafood",
        "available_time_slots": ["19:00", "19:30", "20:30", "21:30"],
        "deposit_per_table": 1800.0,
        "merchant": "Trishna Seafood",
    },
    {
        "restaurant_id": "rest_table_mumbai",
        "restaurant_name": "The Table",
        "city": "Mumbai",
        "area": "Colaba",
        "cuisine": "Modern European",
        "available_time_slots": ["19:00", "20:00", "21:00"],
        "deposit_per_table": 2500.0,
        "merchant": "The Table Restaurant",
    },
    {
        "restaurant_id": "rest_gajalee_mumbai",
        "restaurant_name": "Gajalee",
        "city": "Mumbai",
        "area": "Vile Parle",
        "cuisine": "Maharashtrian Seafood",
        "available_time_slots": ["19:30", "20:30", "21:30"],
        "deposit_per_table": 1200.0,
        "merchant": "Gajalee Coastal",
    },
    {
        "restaurant_id": "rest_bukhara_delhi",
        "restaurant_name": "Bukhara",
        "city": "Delhi",
        "area": "ITC Maurya",
        "cuisine": "North Western Frontier",
        "available_time_slots": ["19:30", "21:00"],
        "deposit_per_table": 3500.0,
        "merchant": "Bukhara Dining",
    },
    {
        "restaurant_id": "rest_karims_delhi",
        "restaurant_name": "Karim's",
        "city": "Delhi",
        "area": "Old Delhi",
        "cuisine": "Mughlai",
        "available_time_slots": ["19:00", "20:00", "21:00"],
        "deposit_per_table": 900.0,
        "merchant": "Karims Historic",
    },
    {
        "restaurant_id": "rest_karavalli_blr",
        "restaurant_name": "Karavalli",
        "city": "Bangalore",
        "area": "Residency Road",
        "cuisine": "South Indian Coastal",
        "available_time_slots": ["19:30", "20:45"],
        "deposit_per_table": 2000.0,
        "merchant": "Karavalli Dining",
    },
]


def search_restaurants(
    city: Optional[str] = None,
    restaurant_name: Optional[str] = None,
    cuisine: Optional[str] = None,
    max_budget: Optional[float] = None,
    time_slot: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Searches available restaurant tables matching city, venue, and deposit budget.
    """
    norm_city = city.strip().lower() if city else None
    norm_venue = restaurant_name.strip().lower() if restaurant_name else None

    results = []
    for r in MOCK_RESTAURANT_INVENTORY:
        if norm_city and norm_city not in r["city"].lower() and norm_city not in r["area"].lower():
            continue
        if norm_venue and norm_venue not in r["restaurant_name"].lower():
            continue
        if cuisine and cuisine.lower() not in r["cuisine"].lower():
            continue
        if max_budget is not None and r["deposit_per_table"] > max_budget:
            continue
        if time_slot and time_slot not in r["available_time_slots"]:
            # If explicit slot requested, check availability
            continue

        results.append(dict(r))

    return results


def select_restaurant(
    city: Optional[str] = None,
    restaurant_name: Optional[str] = None,
    date: Optional[str] = None,
    time_slot: Optional[str] = None,
    party_size: Optional[int] = 2,
    max_budget: Optional[float] = None,
    cuisine: Optional[str] = None,
) -> Optional[SelectedRestaurantOption]:
    """
    Selects the optimal restaurant reservation option satisfying constraints.
    Returns None if no matching restaurant is found.
    """
    restaurants = search_restaurants(
        city=city,
        restaurant_name=restaurant_name,
        cuisine=cuisine,
        max_budget=max_budget,
        time_slot=time_slot,
    )
    if not restaurants:
        return None

    # If venue specified, exact match takes precedence; else lowest deposit
    restaurants.sort(key=lambda x: x["deposit_per_table"])
    best = restaurants[0]

    chosen_time = time_slot if (time_slot and time_slot in best["available_time_slots"]) else best["available_time_slots"][0]

    return SelectedRestaurantOption(
        restaurant_id=best["restaurant_id"],
        restaurant_name=best["restaurant_name"],
        city=best["city"],
        cuisine=best["cuisine"],
        date=date or "2026-09-04",
        time_slot=chosen_time,
        party_size=party_size or 2,
        deposit_amount=float(best["deposit_per_table"]),
        merchant=best.get("merchant", best["restaurant_name"]),
        category="dining",
        currency="INR",
    )
