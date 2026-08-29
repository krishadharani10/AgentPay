# AgentPay Development Rules

## Project

AgentPay is a permissioned payment infrastructure for AI agents.

Core principle:

The LLM may REQUEST a payment, but it must NEVER directly authorize or execute a payment.

All financial authorization decisions MUST pass through the deterministic Policy Engine.

---

## Architecture

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS

### Backend

* Python
* FastAPI
* SQLAlchemy
* PostgreSQL

### AI

* LLM with structured tool/function calling

### Payments

* Razorpay Test Mode
* Payment abstraction layer
* Mock payment adapter for deterministic demo scenarios

---

## Security Rules

1. Never store real card numbers.
2. Never expose Razorpay secrets to the frontend.
3. Never allow the LLM to directly call Razorpay.
4. Every payment must pass through the Policy Engine.
5. Every payment must have an idempotency key.
6. Every payment attempt must create an audit event.
7. Fallback payment methods must also pass policy checks.
8. Never use live payment credentials during development.
9. Never commit `.env` files.
10. Never make payment authorization dependent on LLM reasoning alone.

---

## Coding Rules

* Keep modules small.
* Use type hints.
* Use Pydantic schemas.
* Use environment variables for secrets.
* Write tests for the Policy Engine.
* Write tests for payment state transitions.
* Prefer simple architecture over unnecessary infrastructure.
* Do not introduce Redis, Kafka, Kubernetes, vector databases, or microservices unless explicitly required.

---

## Demo Requirements

The final demo must support:

1. Successful authorized payment.
2. Rejected payment due to policy.
3. Payment failure.
4. Automatic fallback payment.
5. Complete audit trail.
6. Explainable decision shown in the dashboard.
7. Razorpay Test Mode integration.
8. Deterministic Mock Payment Mode for reliable demonstration.
