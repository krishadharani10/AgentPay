"""
LLM Provider Abstraction for AgentPay.

Provides a clean interface for LLM interactions so the orchestration layer
can be tested without requiring a real LLM API key.

SECURITY INVARIANTS:
- The LLM provider only converts natural language → structured TransactionIntent.
- It NEVER makes authorization decisions.
- It NEVER accesses payment adapters, wallets, or databases directly.
- All financial logic is delegated to the deterministic Policy Engine.
"""
import re
from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.agent_types import TransactionIntent


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.
    Implementations may include OpenAI, Gemini, local models, or mock providers.
    """

    @abstractmethod
    def parse_payment_intent(self, message: str) -> TransactionIntent:
        """
        Parse a natural-language payment request into a structured TransactionIntent.

        Args:
            message: User's natural-language payment instruction.

        Returns:
            TransactionIntent with merchant, amount, currency, category, and description.
        """
        pass


class MockLLMProvider(LLMProvider):
    """
    Deterministic Mock LLM Provider for testing and demos.

    Uses keyword matching and regex extraction to simulate LLM behavior
    without requiring any external API. Produces identical results for
    identical inputs — fully deterministic and reproducible.
    """

    def parse_payment_intent(self, message: str) -> TransactionIntent:
        """
        Convert natural-language message into TransactionIntent using
        deterministic keyword matching (no LLM call).
        If amount is omitted in the message, it remains None so it can be
        retrieved dynamically from the database bill via get_bill.
        """
        merchant = self._extract_merchant(message)
        amount = self._extract_amount(message)
        category = self._extract_category(message, merchant)
        description = self._extract_description(message, merchant)

        return TransactionIntent(
            merchant=merchant,
            amount=amount,
            currency="INR",
            category=category,
            description=description,
            bill_id=None,
        )

    @staticmethod
    def _extract_merchant(message: str) -> str:
        """Extract merchant name from message using keyword matching."""
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
        elif "casino" in msg_lower or "gambling" in msg_lower:
            return "Casino Royale"
        return "Unknown Merchant"

    @staticmethod
    def _extract_amount(message: str) -> Optional[float]:
        """Extract numeric amount from message using regex."""
        match = re.search(
            r'(?:₹|rs\.?|inr|\$)?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
            message,
            re.IGNORECASE,
        )
        if match:
            clean_num = match.group(1).replace(",", "")
            try:
                val = float(clean_num)
                if val > 0:
                    return val
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_category(message: str, merchant_name: str) -> str:
        """Determine spending category from message context and merchant."""
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

    @staticmethod
    def _extract_description(message: str, merchant_name: str) -> str:
        """Generate a human-readable description for the payment."""
        msg_lower = message.lower()
        if "bill" in msg_lower:
            return f"Bill payment to {merchant_name}"
        elif "subscription" in msg_lower:
            return f"Subscription payment to {merchant_name}"
        elif "booking" in msg_lower or "book" in msg_lower:
            return f"Booking payment to {merchant_name}"
        return f"Payment to {merchant_name}"
