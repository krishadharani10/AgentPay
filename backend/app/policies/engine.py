from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class RuleResult:
    def __init__(self, rule: str, passed: bool, details: str):
        self.rule = rule
        self.passed = passed
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "passed": self.passed,
            "details": self.details,
        }


class PolicyDecision:
    def __init__(
        self,
        approved: bool,
        decision_code: str,
        reason: str,
        rules_checked: List[Dict[str, Any]],
        remaining_daily_budget: float,
        current_daily_spent: float,
    ):
        self.approved = approved
        self.decision_code = decision_code
        self.reason = reason
        self.rules_checked = rules_checked
        self.remaining_daily_budget = round(remaining_daily_budget, 2)
        self.current_daily_spent = round(current_daily_spent, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "decision_code": self.decision_code,
            "reason": self.reason,
            "rules_checked": self.rules_checked,
            "remaining_daily_budget": self.remaining_daily_budget,
            "current_daily_spent": self.current_daily_spent,
        }


class PolicyEngine:
    """
    Deterministic financial policy engine for AI agents.
    
    CRITICAL: This engine executes purely deterministic logic with zero LLM reasoning.
    Every financial authorization decision must be mathematically and rule-explainable.
    """

    @classmethod
    def evaluate(
        cls,
        *,
        amount: float,
        category: str,
        merchant_name: str,
        current_daily_spent: float = 0.0,
        wallet_status: str = "ACTIVE",
        wallet_per_tx_limit: float = 8000.0,
        wallet_daily_limit: float = 15000.0,
        policy_wallet_enabled: bool = True,
        policy_max_tx_amount: float = 8000.0,
        policy_daily_limit: float = 15000.0,
        allowed_categories: Optional[List[str]] = None,
        blocked_categories: Optional[List[str]] = None,
        allowed_merchants: Optional[List[str]] = None,
        blocked_merchants: Optional[List[str]] = None,
    ) -> PolicyDecision:
        rules_checked: List[Dict[str, Any]] = []
        failures: List[Dict[str, str]] = []

        # Normalize strings for comparison
        norm_category = (category or "").strip().lower()
        norm_merchant = (merchant_name or "").strip().lower()
        
        allowed_cats = [c.strip().lower() for c in (allowed_categories or []) if c.strip()]
        blocked_cats = [c.strip().lower() for c in (blocked_categories or []) if c.strip()]
        allowed_merchs = [m.strip().lower() for m in (allowed_merchants or []) if m.strip()]
        blocked_merchs = [m.strip().lower() for m in (blocked_merchants or []) if m.strip()]

        effective_per_tx_limit = min(wallet_per_tx_limit, policy_max_tx_amount)
        effective_daily_limit = min(wallet_daily_limit, policy_daily_limit)
        remaining_budget = max(0.0, effective_daily_limit - current_daily_spent)

        # 1. Wallet Status & Policy Enabled Check
        wallet_active = (wallet_status or "").upper() == "ACTIVE" and policy_wallet_enabled
        if not wallet_active:
            status_desc = f"Wallet status is '{wallet_status}' and policy_wallet_enabled is {policy_wallet_enabled}."
            rules_checked.append(RuleResult(
                rule="WALLET_STATUS",
                passed=False,
                details=f"Payment rejected: Wallet is not active or is disabled by policy ({status_desc})",
            ).to_dict())
            failures.append({
                "code": "WALLET_DISABLED",
                "reason": f"Wallet is inactive or disabled ({status_desc})",
            })
        else:
            rules_checked.append(RuleResult(
                rule="WALLET_STATUS",
                passed=True,
                details=f"Wallet is ACTIVE and enabled for agent operations.",
            ).to_dict())

        # 2. Per-Transaction Limit Check
        if amount > effective_per_tx_limit:
            rules_checked.append(RuleResult(
                rule="TRANSACTION_LIMIT",
                passed=False,
                details=f"Amount ₹{amount:,.2f} exceeds effective per-transaction limit of ₹{effective_per_tx_limit:,.2f}.",
            ).to_dict())
            failures.append({
                "code": "TX_LIMIT_EXCEEDED",
                "reason": f"Transaction amount ₹{amount:,.2f} exceeds per-transaction limit of ₹{effective_per_tx_limit:,.2f}.",
            })
        else:
            rules_checked.append(RuleResult(
                rule="TRANSACTION_LIMIT",
                passed=True,
                details=f"Amount ₹{amount:,.2f} is within per-transaction limit of ₹{effective_per_tx_limit:,.2f}.",
            ).to_dict())

        # 3. Daily Spending Limit Check
        projected_daily_spent = current_daily_spent + amount
        if projected_daily_spent > effective_daily_limit:
            rules_checked.append(RuleResult(
                rule="DAILY_SPENDING_LIMIT",
                passed=False,
                details=f"Projected daily spend ₹{projected_daily_spent:,.2f} (current ₹{current_daily_spent:,.2f} + requested ₹{amount:,.2f}) exceeds daily limit of ₹{effective_daily_limit:,.2f}. Remaining budget: ₹{remaining_budget:,.2f}.",
            ).to_dict())
            failures.append({
                "code": "DAILY_LIMIT_EXCEEDED",
                "reason": f"Daily spending limit exceeded. Requested ₹{amount:,.2f} exceeds remaining daily budget of ₹{remaining_budget:,.2f}.",
            })
        else:
            rules_checked.append(RuleResult(
                rule="DAILY_SPENDING_LIMIT",
                passed=True,
                details=f"Projected spend ₹{projected_daily_spent:,.2f} is within daily limit of ₹{effective_daily_limit:,.2f}. Remaining after transaction: ₹{(remaining_budget - amount):,.2f}.",
            ).to_dict())

        # 4. Category Rules
        # 4a. Blocked categories
        if norm_category in blocked_cats:
            rules_checked.append(RuleResult(
                rule="CATEGORY_CHECK",
                passed=False,
                details=f"Category '{category}' is explicitly blocked by policy (blocked: {blocked_categories}).",
            ).to_dict())
            failures.append({
                "code": "CATEGORY_BLOCKED",
                "reason": f"Category '{category}' is blocked by policy.",
            })
        # 4b. Allowed categories (if specified)
        elif allowed_cats and norm_category not in allowed_cats:
            rules_checked.append(RuleResult(
                rule="CATEGORY_CHECK",
                passed=False,
                details=f"Category '{category}' is not in allowed list (allowed: {allowed_categories}).",
            ).to_dict())
            failures.append({
                "code": "CATEGORY_NOT_ALLOWED",
                "reason": f"Category '{category}' is not in policy allowed categories list.",
            })
        else:
            rules_checked.append(RuleResult(
                rule="CATEGORY_CHECK",
                passed=True,
                details=f"Category '{category}' satisfies category policy rules.",
            ).to_dict())

        # 5. Merchant Rules
        # 5a. Blocked merchants
        if norm_merchant in blocked_merchs:
            rules_checked.append(RuleResult(
                rule="MERCHANT_CHECK",
                passed=False,
                details=f"Merchant '{merchant_name}' is explicitly blocked by policy (blocked: {blocked_merchants}).",
            ).to_dict())
            failures.append({
                "code": "MERCHANT_BLOCKED",
                "reason": f"Merchant '{merchant_name}' is blocked by policy.",
            })
        # 5b. Allowed merchants (if whitelist specified)
        elif allowed_merchs and norm_merchant not in allowed_merchs:
            rules_checked.append(RuleResult(
                rule="MERCHANT_CHECK",
                passed=False,
                details=f"Merchant '{merchant_name}' is not in allowed list (allowed: {allowed_merchants}).",
            ).to_dict())
            failures.append({
                "code": "MERCHANT_NOT_ALLOWED",
                "reason": f"Merchant '{merchant_name}' is not in policy allowed merchants list.",
            })
        else:
            rules_checked.append(RuleResult(
                rule="MERCHANT_CHECK",
                passed=True,
                details=f"Merchant '{merchant_name}' satisfies merchant policy rules.",
            ).to_dict())

        # Evaluate final verdict
        if not failures:
            final_remaining_budget = max(0.0, remaining_budget - amount)
            return PolicyDecision(
                approved=True,
                decision_code="APPROVED",
                reason=f"Payment of ₹{amount:,.2f} for '{merchant_name}' ({category}) complies with all wallet and policy rules.",
                rules_checked=rules_checked,
                remaining_daily_budget=final_remaining_budget,
                current_daily_spent=current_daily_spent,
            )
        elif len(failures) == 1:
            return PolicyDecision(
                approved=False,
                decision_code=failures[0]["code"],
                reason=failures[0]["reason"],
                rules_checked=rules_checked,
                remaining_daily_budget=remaining_budget,
                current_daily_spent=current_daily_spent,
            )
        else:
            combined_reasons = "; ".join([f["reason"] for f in failures])
            return PolicyDecision(
                approved=False,
                decision_code="MULTIPLE_POLICY_VIOLATIONS",
                reason=f"Multiple policy checks failed: {combined_reasons}",
                rules_checked=rules_checked,
                remaining_daily_budget=remaining_budget,
                current_daily_spent=current_daily_spent,
            )
