"""
LLM Provider Abstraction for AgentPay.

Provides a clean interface for LLM interactions so the orchestration layer
can be tested without requiring a real LLM API key.

SECURITY INVARIANTS:
- The LLM provider only converts natural language → structured TaskIntent / TransactionIntent.
- It NEVER makes authorization decisions.
- It NEVER accesses payment adapters, wallets, or databases directly.
- All financial logic is delegated to the deterministic Policy Engine.
"""
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from app.schemas.agent_types import TransactionIntent
from app.schemas.task_types import TaskType, TaskIntent


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.
    Implementations may include OpenAI, Gemini, local models, or mock providers.
    """

    @abstractmethod
    def parse_payment_intent(self, message: str) -> TransactionIntent:
        """
        Parse a natural-language payment request into a structured TransactionIntent.
        """
        pass

    def parse_task_intent(self, message: str) -> TaskIntent:
        """
        Parse a natural-language commercial goal into a structured TaskIntent.
        Default fallback creates a DIRECT_PAYMENT TaskIntent from parse_payment_intent.
        """
        pi = self.parse_payment_intent(message)
        return TaskIntent(
            task_type=TaskType.DIRECT_PAYMENT,
            user_message=message,
            merchant=pi.merchant,
            budget=pi.amount,
            max_budget=pi.amount,
            category=pi.category,
        )



class MockLLMProvider(LLMProvider):
    """
    Deterministic Mock LLM Provider for testing and demos.

    Uses keyword matching and regex extraction to simulate LLM behavior
    without requiring any external API. Produces identical results for
    identical inputs — fully deterministic and reproducible.
    """

    def parse_task_intent(self, message: str) -> TaskIntent:
        """
        Convert natural-language message into TaskIntent using deterministic
        intent classification and entity extraction.
        """
        msg_lower = message.lower()

        # 1. Classify Flight Booking Task
        if any(w in msg_lower for w in ["flight", "fly", "plane", "airline", "book ticket", "flight ticket"]):
            origin, dest = self._extract_flight_route(message)
            budget = self._extract_amount(message)
            date = self._extract_date(message) or "2026-09-10"
            airline = self._extract_airline(message)

            return TaskIntent(
                task_type=TaskType.BOOK_FLIGHT,
                user_message=message,
                origin=origin or "BOM",
                destination=dest or "DEL",
                budget=budget,
                max_budget=budget,
                date=date,
                merchant=airline or "MakeMyTrip",
                category="travel",
                metadata={"preferred_airline": airline} if airline else {},
            )

        # 2. Classify Restaurant Reservation Task
        if any(w in msg_lower for w in [
            "restaurant", "table", "reserve", "reservation", "dinner", "lunch",
            "bukhara", "trishna", "gajalee", "karavalli", "itc", "narmada", "charcoal", "pepito"
        ]):
            venue = self._extract_restaurant_name(message)
            city = self._extract_city(message)
            party_size = self._extract_party_size(message) or 2
            budget = self._extract_amount(message)
            date = self._extract_date(message) or "2026-09-22"
            time_slot = self._extract_time(message)

            return TaskIntent(
                task_type=TaskType.RESERVE_RESTAURANT,
                user_message=message,
                city=city or "Ahmedabad",
                merchant=venue,
                party_size=party_size,
                budget=budget,
                max_budget=budget,
                date=date,
                time=time_slot,
                category="dining",
                metadata={"venue": venue} if venue else {},
            )

        # 3. Default to Direct Payment Task
        merchant = self._extract_merchant(message)
        amount = self._extract_amount(message)
        category = self._extract_category(message, merchant)

        return TaskIntent(
            task_type=TaskType.DIRECT_PAYMENT,
            user_message=message,
            merchant=merchant,
            budget=amount,
            max_budget=amount,
            category=category,
        )

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
    def _extract_flight_route(message: str) -> tuple[Optional[str], Optional[str]]:
        """Extract origin and destination from flight booking message."""
        msg_lower = message.lower()
        origin = None
        destination = None

        # Pattern 1: from X to Y (e.g. "from Ahmedabad to Mumbai", "from AMD to BOM")
        from_to_match = re.search(
            r'from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+?)(?:\s+on|\s+under|\s+for|\s+with|\s+at|\s+in|\s*$)',
            message,
            re.IGNORECASE,
        )
        if from_to_match:
            origin = from_to_match.group(1).strip()
            destination = from_to_match.group(2).strip()
            return origin, destination

        # Pattern 2: X to Y (e.g. "AMD to BOM", "Ahmedabad to Mumbai flight")
        route_match = re.search(
            r'\b([A-Za-z]{3,15})\s+to\s+([A-Za-z]{3,15})\b',
            message,
            re.IGNORECASE,
        )
        if route_match:
            origin = route_match.group(1).strip()
            destination = route_match.group(2).strip()
            return origin, destination

        # Pattern 3: City heuristics
        if "ahmedabad" in msg_lower or "amd" in msg_lower:
            origin = "Ahmedabad"
            if "mumbai" in msg_lower or "bom" in msg_lower:
                destination = "Mumbai"
            elif "delhi" in msg_lower or "del" in msg_lower:
                destination = "Delhi"
            return origin, destination

        if "delhi" in msg_lower:
            destination = "Delhi"
            origin = "Mumbai"
        elif "bangalore" in msg_lower or "blr" in msg_lower:
            destination = "Bangalore"
            origin = "Mumbai"
        elif "goa" in msg_lower:
            destination = "Goa"
            origin = "Mumbai"

        return origin, destination

    @staticmethod
    def _extract_airline(message: str) -> Optional[str]:
        msg_lower = message.lower()
        if "airdemo" in msg_lower or "air demo" in msg_lower:
            return "AirDemo"
        elif "indigo" in msg_lower:
            return "IndiGo"
        elif "air india" in msg_lower or "airindia" in msg_lower:
            return "Air India"
        elif "spicejet" in msg_lower:
            return "SpiceJet"
        elif "akasa" in msg_lower:
            return "Akasa Air"
        elif "vistara" in msg_lower:
            return "Vistara"
        return None

    @staticmethod
    def _extract_restaurant_name(message: str) -> Optional[str]:
        msg_lower = message.lower()
        if "itc narmada" in msg_lower or "narmada" in msg_lower:
            return "ITC Narmada"
        elif "charcoal" in msg_lower:
            return "K's Charcoal"
        elif "pepito" in msg_lower:
            return "Pepito"
        elif "trishna" in msg_lower:
            return "Trishna"
        elif "the table" in msg_lower or "table colaba" in msg_lower:
            return "The Table"
        elif "bukhara" in msg_lower:
            return "Bukhara"
        elif "gajalee" in msg_lower:
            return "Gajalee"
        elif "karavalli" in msg_lower:
            return "Karavalli"
        elif "karim" in msg_lower:
            return "Karim's"
        return None

    @staticmethod
    def _extract_city(message: str) -> Optional[str]:
        msg_lower = message.lower()
        if "ahmedabad" in msg_lower or "amd" in msg_lower:
            return "Ahmedabad"
        elif "mumbai" in msg_lower or "bombay" in msg_lower:
            return "Mumbai"
        elif "delhi" in msg_lower:
            return "Delhi"
        elif "bangalore" in msg_lower or "bengaluru" in msg_lower:
            return "Bangalore"
        elif "goa" in msg_lower:
            return "Goa"
        return None

    @staticmethod
    def _extract_party_size(message: str) -> Optional[int]:
        # Matches: "for 2 people", "for 2 persons", "for 2", "number of person 2", "party of 5", "table for 4"
        match = re.search(r'(?:for|party of|table for|number of persons?)\s+(\d+)', message, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        # Fallback: "2 people", "5 persons", "2 guests"
        match_guests = re.search(r'\b(\d+)\s*(?:people|persons?|guests?)\b', message, re.IGNORECASE)
        if match_guests:
            try:
                return int(match_guests.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_time(message: str) -> Optional[str]:
        # Match time patterns like: "at 8:30 PM", "8:00 PM", "8 PM", "8:30 pm", "20:00"
        match = re.search(r'(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:pm|am))', message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match_24 = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', message)
        if match_24:
            return f"{int(match_24.group(1)):02d}:{match_24.group(2)}"
        if "dinner" in message.lower() or "night" in message.lower():
            return "8:00 PM"
        elif "lunch" in message.lower():
            return "1:00 PM"
        return None

    @staticmethod
    def _extract_date(message: str) -> Optional[str]:
        """Extract ISO date string (YYYY-MM-DD) from message."""
        # 1. ISO format: 2026-09-05 or 2026-09-22
        iso_match = re.search(r'\b(202\d)-(\d{1,2})-(\d{1,2})\b', message)
        if iso_match:
            year, month, day = iso_match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"

        # 2. Month name format: "September 22", "September 5, 2026", "Sep 22", "22 September"
        months = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }

        # Pattern: Month Day (e.g. "September 22", "Sep 5, 2026")
        month_day_match = re.search(
            r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b',
            message,
            re.IGNORECASE,
        )
        if month_day_match:
            m_str, d_str, y_str = month_day_match.groups()
            m_num = months.get(m_str.lower(), 9)
            d_num = int(d_str)
            y_num = int(y_str) if y_str else 2026
            return f"{y_num:04d}-{m_num:02d}-{d_num:02d}"

        # Pattern: Day Month (e.g. "22nd September 2026", "5 September")
        day_month_match = re.search(
            r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:,?\s+(\d{4}))?\b',
            message,
            re.IGNORECASE,
        )
        if day_month_match:
            d_str, m_str, y_str = day_month_match.groups()
            m_num = months.get(m_str.lower(), 9)
            d_num = int(d_str)
            y_num = int(y_str) if y_str else 2026
            return f"{y_num:04d}-{m_num:02d}-{d_num:02d}"

        # 3. Relative keywords
        msg_lower = message.lower()
        if "friday" in msg_lower:
            return "2026-09-11"
        elif "tomorrow" in msg_lower:
            return "2026-09-05"
        elif "tonight" in msg_lower or "today" in msg_lower:
            return "2026-09-04"

        return None

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
        """Extract numeric amount from message using prioritized regex."""
        # 1. Explicit currency symbol: ₹1,240 or Rs 1240 or $1240 or INR 1240
        match = re.search(
            r'(?:₹|rs\.?|inr|\$)\s*(\d+(?:,\d+)*(?:\.\d+)?)',
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

        # 2. Budget / under / max keywords: under 5000, max 2000, budget of 3000
        match_budget = re.search(
            r'(?:under|max|budget(?: of)?|upto|cap of)\s*(?:₹|rs\.?|inr|\$)?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
            message,
            re.IGNORECASE,
        )
        if match_budget:
            clean_num = match_budget.group(1).replace(",", "")
            try:
                val = float(clean_num)
                if val > 0:
                    return val
            except ValueError:
                pass

        # 3. Fallback: standalone number >= 50 (avoids matching party sizes like 2 or 4)
        matches = re.findall(r'\b(\d+(?:,\d+)*(?:\.\d+)?)\b', message)
        for m in matches:
            clean_num = m.replace(",", "")
            try:
                val = float(clean_num)
                if val >= 50:
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
        elif any(r in msg_lower for r in ["restaurant", "table", "dinner", "dining", "trishna", "bukhara"]):
            return "dining"
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
