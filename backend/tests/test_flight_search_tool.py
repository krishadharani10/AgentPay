"""
Unit tests for the deterministic Flight Search Tool (app/tools/flight_search.py).
"""
import pytest
from app.tools.flight_search import (
    search_flights,
    select_cheapest_flight,
    flight_to_transaction_dict,
    FlightSearchResult,
    FlightRecord,
)


class TestFlightSearchTool:

    def test_search_amd_to_bom_september_5_all_inventory(self):
        """
        Verify search for AMD → BOM on September 5, 2026 returns all 3 deterministic flights:
        - AP101 (₹7,450)
        - AP205 (₹8,250)
        - AP420 (₹11,500)
        """
        result: FlightSearchResult = search_flights(
            origin="AMD",
            destination="BOM",
            date="2026-09-05",
            max_budget=None,
        )

        assert result.found_any is True
        assert len(result.all_options) == 3

        prices = [f.price for f in result.all_options]
        assert 7450.0 in prices
        assert 8250.0 in prices
        assert 11500.0 in prices

        flight_numbers = [f.flight_number for f in result.all_options]
        assert "AP101" in flight_numbers
        assert "AP205" in flight_numbers
        assert "AP420" in flight_numbers

    def test_search_amd_to_bom_city_name_normalization(self):
        """
        Verify city names ('Ahmedabad', 'Mumbai') are normalized to IATA codes ('AMD', 'BOM').
        """
        result = search_flights(
            origin="Ahmedabad",
            destination="Mumbai",
            date="2026-09-05",
        )
        assert result.search_origin == "AMD"
        assert result.search_destination == "BOM"
        assert len(result.all_options) == 3

    def test_search_budget_filter_10000(self):
        """
        Budget ₹10,000 should filter out the ₹11,500 Business flight and retain AP101 & AP205.
        """
        result = search_flights(
            origin="AMD",
            destination="BOM",
            date="2026-09-05",
            max_budget=10000.0,
        )
        assert len(result.all_options) == 3
        assert len(result.filtered_options) == 2
        assert all(f.price <= 10000.0 for f in result.filtered_options)

    def test_search_budget_filter_8000(self):
        """
        Budget ₹8,000 should only retain AP101 (₹7,450).
        """
        result = search_flights(
            origin="AMD",
            destination="BOM",
            date="2026-09-05",
            max_budget=8000.0,
        )
        assert len(result.filtered_options) == 1
        assert result.filtered_options[0].flight_number == "AP101"
        assert result.filtered_options[0].price == 7450.0

    def test_search_budget_too_low(self):
        """
        Budget ₹5,000 for AMD → BOM should find flights but 0 within budget.
        """
        result = search_flights(
            origin="AMD",
            destination="BOM",
            date="2026-09-05",
            max_budget=5000.0,
        )
        assert result.found_any is True
        assert result.found_within_budget is False
        assert len(result.filtered_options) == 0
        assert "none within budget" in result.summary()

    def test_search_unknown_route(self):
        """
        Searching a non-existent route should return 0 options.
        """
        result = search_flights(
            origin="AMD",
            destination="CCU",
            date="2026-09-05",
        )
        assert result.found_any is False
        assert len(result.all_options) == 0
        assert len(result.filtered_options) == 0

    def test_select_cheapest_flight(self):
        """
        select_cheapest_flight deterministically picks the lowest price flight.
        """
        result = search_flights(
            origin="AMD",
            destination="BOM",
            date="2026-09-05",
            max_budget=10000.0,
        )
        cheapest = select_cheapest_flight(result)
        assert cheapest is not None
        assert cheapest.flight_number == "AP101"
        assert cheapest.price == 7450.0

    def test_select_cheapest_when_no_options_returns_none(self):
        """
        select_cheapest_flight returns None when filtered_options is empty.
        """
        result = search_flights(
            origin="AMD",
            destination="BOM",
            date="2026-09-05",
            max_budget=500.0,
        )
        assert select_cheapest_flight(result) is None

    def test_flight_to_transaction_dict_converts_correctly(self):
        """
        Verify FlightRecord converts to standard AgentPay TransactionIntent dictionary.
        """
        result = search_flights(
            origin="AMD",
            destination="BOM",
            date="2026-09-05",
            max_budget=8000.0,
        )
        flight = select_cheapest_flight(result)
        assert flight is not None

        tx_dict = flight_to_transaction_dict(flight)
        assert tx_dict["merchant"] == "AirDemo"
        assert tx_dict["amount"] == 7450.0
        assert tx_dict["currency"] == "INR"
        assert tx_dict["category"] == "travel"
        assert "AP101 AMD→BOM" in tx_dict["description"]
