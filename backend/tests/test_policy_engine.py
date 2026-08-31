import pytest
from app.policies.engine import PolicyEngine


class TestPolicyEngine:
    def test_valid_transaction_approved(self):
        """Test valid transaction under limits and with allowed category."""
        decision = PolicyEngine.evaluate(
            amount=1240.0,
            category="utilities",
            merchant_name="Torrent Power",
            current_daily_spent=0.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=True,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            blocked_categories=["gambling", "crypto"],
        )
        assert decision.approved is True
        assert decision.decision_code == "APPROVED"
        assert decision.remaining_daily_budget == 8760.0  # 10000 - 1240
        assert len(decision.rules_checked) == 5
        assert all(rule["passed"] for rule in decision.rules_checked)

    def test_transaction_exactly_at_limit(self):
        """Test transaction where amount equals per-transaction limit."""
        decision = PolicyEngine.evaluate(
            amount=5000.0,
            category="subscriptions",
            merchant_name="Netflix",
            current_daily_spent=0.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=True,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            blocked_categories=["gambling", "crypto"],
        )
        assert decision.approved is True
        assert decision.decision_code == "APPROVED"
        assert decision.remaining_daily_budget == 5000.0

    def test_transaction_above_per_tx_limit_rejected(self):
        """Test transaction exceeding per-transaction limit (e.g. ₹6,000 > ₹5,000)."""
        decision = PolicyEngine.evaluate(
            amount=6000.0,
            category="travel",
            merchant_name="MakeMyTrip",
            current_daily_spent=0.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=True,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            blocked_categories=["gambling", "crypto"],
        )
        assert decision.approved is False
        assert decision.decision_code == "TX_LIMIT_EXCEEDED"
        assert "exceeds" in decision.reason.lower()

    def test_daily_spending_limit_exceeded(self):
        """Test transaction exceeding remaining daily spending limit."""
        decision = PolicyEngine.evaluate(
            amount=2000.0,
            category="subscriptions",
            merchant_name="Spotify",
            current_daily_spent=9000.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=True,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            blocked_categories=["gambling", "crypto"],
        )
        assert decision.approved is False
        assert decision.decision_code == "DAILY_LIMIT_EXCEEDED"
        assert decision.remaining_daily_budget == 1000.0

    def test_blocked_category_rejected(self):
        """Test transaction with category in blocked_categories list."""
        for blocked_cat in ["gambling", "crypto", "GAMBLING"]:
            decision = PolicyEngine.evaluate(
                amount=500.0,
                category=blocked_cat,
                merchant_name="Crypto Exchange",
                current_daily_spent=0.0,
                wallet_status="ACTIVE",
                wallet_per_tx_limit=5000.0,
                wallet_daily_limit=10000.0,
                policy_wallet_enabled=True,
                policy_max_tx_amount=5000.0,
                policy_daily_limit=10000.0,
                allowed_categories=["utilities", "subscriptions", "travel"],
                blocked_categories=["gambling", "crypto"],
            )
            assert decision.approved is False
            assert decision.decision_code == "CATEGORY_BLOCKED"

    def test_category_not_in_allowed_list_rejected(self):
        """Test transaction category not included in allowed whitelist."""
        decision = PolicyEngine.evaluate(
            amount=500.0,
            category="gaming",
            merchant_name="Steam",
            current_daily_spent=0.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=True,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            blocked_categories=["gambling", "crypto"],
        )
        assert decision.approved is False
        assert decision.decision_code == "CATEGORY_NOT_ALLOWED"

    def test_blocked_merchant_rejected(self):
        """Test transaction with merchant explicitly blocked."""
        decision = PolicyEngine.evaluate(
            amount=500.0,
            category="travel",
            merchant_name="Untrusted Airlines",
            current_daily_spent=0.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=True,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            blocked_merchants=["Untrusted Airlines"],
        )
        assert decision.approved is False
        assert decision.decision_code == "MERCHANT_BLOCKED"

    def test_merchant_not_allowed_in_whitelist(self):
        """Test transaction when allowed_merchants whitelist is active and merchant is omitted."""
        decision = PolicyEngine.evaluate(
            amount=500.0,
            category="travel",
            merchant_name="Unknown Travels",
            current_daily_spent=0.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=True,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            allowed_merchants=["MakeMyTrip", "Torrent Power"],
        )
        assert decision.approved is False
        assert decision.decision_code == "MERCHANT_NOT_ALLOWED"

    def test_wallet_status_disabled_rejected(self):
        """Test when wallet status is DISABLED or FROZEN."""
        for status in ["DISABLED", "FROZEN"]:
            decision = PolicyEngine.evaluate(
                amount=500.0,
                category="utilities",
                merchant_name="Torrent Power",
                current_daily_spent=0.0,
                wallet_status=status,
                wallet_per_tx_limit=5000.0,
                wallet_daily_limit=10000.0,
                policy_wallet_enabled=True,
                policy_max_tx_amount=5000.0,
                policy_daily_limit=10000.0,
            )
            assert decision.approved is False
            assert decision.decision_code == "WALLET_DISABLED"

    def test_policy_wallet_disabled_flag(self):
        """Test when policy.wallet_enabled is False."""
        decision = PolicyEngine.evaluate(
            amount=500.0,
            category="utilities",
            merchant_name="Torrent Power",
            current_daily_spent=0.0,
            wallet_status="ACTIVE",
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=False,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
        )
        assert decision.approved is False
        assert decision.decision_code == "WALLET_DISABLED"

    def test_multiple_rule_failures(self):
        """Test when multiple rules fail simultaneously."""
        decision = PolicyEngine.evaluate(
            amount=7500.0,  # Exceeds per tx limit (5000)
            category="gambling",  # Blocked category
            merchant_name="Casino Royal",
            current_daily_spent=0.0,
            wallet_status="DISABLED",  # Disabled wallet
            wallet_per_tx_limit=5000.0,
            wallet_daily_limit=10000.0,
            policy_wallet_enabled=False,
            policy_max_tx_amount=5000.0,
            policy_daily_limit=10000.0,
            allowed_categories=["utilities"],
            blocked_categories=["gambling"],
        )
        assert decision.approved is False
        assert decision.decision_code == "MULTIPLE_POLICY_VIOLATIONS"
        failed_rules = [r for r in decision.rules_checked if not r["passed"]]
        assert len(failed_rules) >= 3
