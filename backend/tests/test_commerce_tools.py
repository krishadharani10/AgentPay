"""
Unit tests for Autonomous Commerce Tools (Flight Booking & Restaurant Reservation).
"""
import pytest
from app.agents.commerce_tools import (
    search_flights,
    select_flight,
    search_restaurants,
    select_restaurant,
)
from app.schemas.task_types import SelectedFlightOption, SelectedRestaurantOption
from app.schemas.agent_types import TransactionIntent


class TestFlightCommerceTool:
    def test_search_flights_route_matching(self):
        """Search flights matches origin and destination properly."""
        flights = search_flights(origin="Mumbai", destination="Delhi")
        assert len(flights) >= 2
        for f in flights:
            assert f["origin"] == "BOM"
            assert f["destination"] == "DEL"

    def test_search_flights_budget_filter(self):
        """Flights above max_budget are excluded."""
        cheap_flights = search_flights(origin="BOM", destination="DEL", max_budget=4000.0)
        assert len(cheap_flights) == 1
        assert cheap_flights[0]["airline"] == "SpiceJet"
        assert cheap_flights[0]["price"] == 3800.0

    def test_select_flight_chooses_lowest_price(self):
        """select_flight picks lowest price option within budget."""
        selected = select_flight(origin="BOM", destination="DEL", max_budget=5000.0)
        assert selected is not None
        assert isinstance(selected, SelectedFlightOption)
        assert selected.price == 3800.0  # SpiceJet 3800 < IndiGo 4500
        assert selected.airline == "SpiceJet"

    def test_select_flight_no_match_returns_none(self):
        """Returns None if budget is too low for any flight."""
        selected = select_flight(origin="BOM", destination="DEL", max_budget=1000.0)
        assert selected is None

    def test_flight_to_transaction_intent_conversion(self):
        """SelectedFlightOption converts cleanly into standard TransactionIntent."""
        flight = SelectedFlightOption(
            flight_id="flt_test_01",
            airline="IndiGo",
            flight_number="6E-204",
            origin="BOM",
            destination="DEL",
            departure_time="06:00",
            arrival_time="08:15",
            date="2026-09-10",
            price=4500.0,
            merchant="MakeMyTrip",
            category="travel",
            currency="INR",
        )
        tx_intent = flight.to_transaction_intent()
        assert isinstance(tx_intent, TransactionIntent)
        assert tx_intent.merchant == "MakeMyTrip"
        assert tx_intent.amount == 4500.0
        assert tx_intent.category == "travel"
        assert "6E-204" in tx_intent.description


class TestRestaurantCommerceTool:
    def test_search_restaurants_by_city(self):
        """Search restaurants finds venues in target city."""
        mumbai_rests = search_restaurants(city="Mumbai")
        assert len(mumbai_rests) >= 3
        for r in mumbai_rests:
            assert r["city"] == "Mumbai"

    def test_search_restaurants_by_name(self):
        """Search by restaurant name finds specific venue."""
        results = search_restaurants(city="Mumbai", restaurant_name="Trishna")
        assert len(results) == 1
        assert results[0]["restaurant_name"] == "Trishna"
        assert results[0]["deposit_per_table"] == 1800.0

    def test_select_restaurant_budget_filter(self):
        """select_restaurant respects max_budget for deposit."""
        selected = select_restaurant(city="Mumbai", max_budget=1500.0)
        assert selected is not None
        assert isinstance(selected, SelectedRestaurantOption)
        assert selected.restaurant_name == "Gajalee"
        assert selected.deposit_amount == 1200.0

    def test_select_restaurant_no_match_returns_none(self):
        """Returns None if no restaurant meets the budget or venue criteria."""
        selected = select_restaurant(city="Mumbai", max_budget=500.0)
        assert selected is None

    def test_restaurant_to_transaction_intent_conversion(self):
        """SelectedRestaurantOption converts cleanly into standard TransactionIntent."""
        restaurant = SelectedRestaurantOption(
            restaurant_id="rest_trishna",
            restaurant_name="Trishna",
            city="Mumbai",
            cuisine="Seafood",
            date="2026-09-04",
            time_slot="20:30",
            party_size=4,
            deposit_amount=1800.0,
            merchant="Trishna Seafood",
            category="dining",
            currency="INR",
        )
        tx_intent = restaurant.to_transaction_intent()
        assert isinstance(tx_intent, TransactionIntent)
        assert tx_intent.merchant == "Trishna Seafood"
        assert tx_intent.amount == 1800.0
        assert tx_intent.category == "dining"
        assert "party for 4" in tx_intent.description or "Table reservation for 4" in tx_intent.description
