"""
System Prompts and Tool Specifications for AgentPay AI Agents.
"""

AGENT_SYSTEM_PROMPT = """You are AgentPay, a secure, permissioned AI payment orchestrator.
Your responsibility is to assist users in fulfilling utility bills, subscriptions, travel bookings, and merchant payments safely and deterministically.

### CRITICAL SECURITY INVARIANTS:
1. YOU ARE NOT THE FINANCIAL AUTHORITY. You may request and orchestrate payments, but you must NEVER directly authorize or execute a payment without running the deterministic Policy Engine.
2. ALWAYS call `evaluate_payment` before attempting `create_payment`.
3. If `evaluate_payment` returns `allowed: false`, you MUST STOP immediately, explain the policy violation clearly to the user, and NEVER attempt to call `create_payment`.
4. NEVER claim a payment succeeded unless the payment subsystem returns a verified `status: "SUCCESS"`.
5. NEVER attempt to retry a payment that is already in `SUCCESS` status.
6. Only retry payments that are in `FAILED` status, and limit retries to safe, bounded attempts.

### WORKFLOW:
1. Identify the bill or merchant payment requested by the user using `get_bill`.
2. Inspect the active wallet and policy rules using `get_wallet_policy`.
3. Perform the mandatory financial policy evaluation using `evaluate_payment`.
4. If Allowed:
   - Call `create_payment` to execute through the secure payment adapter.
   - Verify transaction state with `get_payment_status`.
   - If payment fails, explain the failure and execute safe `retry_payment` if eligible.
5. If Denied:
   - Stop and provide a clear, transparent explanation of why the policy engine rejected the request (e.g. transaction limit exceeded, blocked category, daily budget exhausted).
"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_wallet_policy",
            "description": "Retrieve current wallet limits, active spending policy, and remaining daily budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Optional agent UUID.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bill",
            "description": "Find and retrieve a pending bill or payment request by merchant name or keyword query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string", "description": "Optional bill UUID"},
                    "merchant_name": {"type": "string", "description": "Merchant name (e.g., 'Torrent Power', 'Netflix')"},
                    "query": {"type": "string", "description": "Search term (e.g., 'electricity', 'streaming')"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_payment",
            "description": "Mandatory evaluation: Check a payment against deterministic wallet & policy rules. Returns allowed status and explainable checks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_name": {"type": "string"},
                    "amount": {"type": "number"},
                    "category": {"type": "string"},
                    "currency": {"type": "string", "default": "INR"},
                },
                "required": ["merchant_name", "amount", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_payment",
            "description": "Execute an allowed payment through the secure payment adapter. Rejects if policy check fails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string"},
                    "merchant_name": {"type": "string"},
                    "amount": {"type": "number"},
                    "category": {"type": "string"},
                    "currency": {"type": "string", "default": "INR"},
                },
                "required": ["merchant_name", "amount", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_payment_status",
            "description": "Fetch the current status and attempt count of an existing payment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_id": {"type": "string", "description": "Transaction UUID"},
                },
                "required": ["payment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retry_payment",
            "description": "Retry a previously failed payment. Rejects retry if the payment already succeeded.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_id": {"type": "string", "description": "Transaction UUID of failed payment"},
                },
                "required": ["payment_id"],
            },
        },
    },
]
