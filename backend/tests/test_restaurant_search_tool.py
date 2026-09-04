"""
Unit tests for the deterministic Restaurant Search Tool (app/tools/restaurant_search.py).
"""
import pytest
from app.tools.restaurant_search import (
    search_restaurants,
    select_cheapest_restaurant,
    restaurant_to_transaction_dict,
    RestaurantSearchResult,
    RestaurantRecord,
)


class TestRestaurantSearchTool:

    def test_search_ahmedabad_itc_narmada(self):
        """
        Search ITC Narmada in Ahmedabad on Sept 22, 2026 for 2 people at 8:00 PM.
        Expects deposit of ₹1,000.
        """
        result: RestaurantSearchResult = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            time="8:00 PM",
            party_size=2,
            restaurant_name="ITC Narmada",
            max_budget=3000.0,
        )

        assert result.found_any is True
        assert len(result.filtered_options) == 1
        option = result.filtered_options[0]
        assert option.restaurant_name == "ITC Narmada"
        assert option.city == "Ahmedabad"
        assert option.date == "2026-09-22"
        assert option.time == "20:00"
        assert option.persons == 2
        assert option.deposit_amount == 1000.0
        assert option.category == "dining"

    def test_search_ahmedabad_ks_charcoal(self):
        """
        Search K's Charcoal in Ahmedabad on Sept 22, 2026 for 5 people at 8:30 PM.
        Expects deposit of ₹600.
        """
        result: RestaurantSearchResult = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            time="8:30 PM",
            party_size=5,
            restaurant_name="K's Charcoal",
        )

        assert result.found_any is True
        assert len(result.filtered_options) == 1
        option = result.filtered_options[0]
        assert option.restaurant_name == "K's Charcoal"
        assert option.persons == 5
        assert option.deposit_amount == 600.0

    def test_search_ahmedabad_pepito(self):
        """
        Search Pepito in Ahmedabad on Sept 22, 2026 for 4 people at 8:00 PM.
        Expects deposit of ₹800.
        """
        result: RestaurantSearchResult = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            time="8:00 PM",
            party_size=4,
            restaurant_name="Pepito",
        )

        assert result.found_any is True
        assert len(result.filtered_options) == 1
        option = result.filtered_options[0]
        assert option.restaurant_name == "Pepito"
        assert option.persons == 4
        assert option.deposit_amount == 800.0

    def test_search_multiple_options_deterministic_lowest_deposit(self):
        """
        When searching Ahmedabad on Sept 22 for 2 people without restaurant name constraint:
        Finds all restaurants with capacity >= 2 (ITC Narmada ₹1000, K's Charcoal ₹600, Pepito ₹800).
        select_cheapest_restaurant deterministically chooses the lowest deposit (K's Charcoal ₹600).
        """
        result = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            party_size=2,
            max_budget=2000.0,
        )

        assert len(result.filtered_options) == 3
        cheapest = select_cheapest_restaurant(result)
        assert cheapest is not None
        assert cheapest.restaurant_name == "K's Charcoal"
        assert cheapest.deposit_amount == 600.0

    def test_search_budget_filtering(self):
        """
        Deposit budget ₹700 should only retain K's Charcoal (₹600) and filter out Pepito (₹800) and ITC (₹1000).
        """
        result = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            party_size=2,
            max_budget=700.0,
        )

        assert len(result.filtered_options) == 1
        assert result.filtered_options[0].restaurant_name == "K's Charcoal"
        assert result.filtered_options[0].deposit_amount == 600.0

    def test_search_party_size_capacity_filtering(self):
        """
        Party of 5 people should only match K's Charcoal (capacity 5), not ITC (2) or Pepito (4).
        """
        result = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            party_size=5,
        )

        assert len(result.filtered_options) == 1
        assert result.filtered_options[0].restaurant_name == "K's Charcoal"

    def test_search_party_size_exceeds_all_capacity(self):
        """
        Party of 10 people has no matching tables.
        """
        result = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            party_size=10,
        )

        assert result.found_any is False
        assert len(result.filtered_options) == 0

    def test_search_budget_too_low(self):
        """
        Budget ₹300 finds options in Ahmedabad, but none within budget.
        """
        result = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            party_size=2,
            max_budget=300.0,
        )

        assert result.found_any is True
        assert result.found_within_budget is False
        assert len(result.filtered_options) == 0

    def test_restaurant_to_transaction_dict_semantics(self):
        """
        Verify restaurant reservation record converts into TransactionIntent dictionary
        with deposit amount semantics and dining category.
        """
        result = search_restaurants(
            city="Ahmedabad",
            date="2026-09-22",
            restaurant_name="ITC Narmada",
            party_size=2,
        )
        selected = select_cheapest_restaurant(result)
        assert selected is not None

        tx_dict = restaurant_to_transaction_dict(selected, party_size=2)
        assert tx_dict["merchant"] == "ITC Narmada"
        assert tx_dict["amount"] == 1000.0
        assert tx_dict["currency"] == "INR"
        assert tx_dict["category"] == "dining"
        assert "reservation deposit for 2 people" in tx_dict["description"].lower()
