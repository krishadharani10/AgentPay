# AgentPay 🛡️💳

**Permissioned Payment Infrastructure for Autonomous AI Agents**

AgentPay is a secure payment layer designed for AI agents.

### Core Architectural Principle
> The LLM may **REQUEST** a payment, but it must **NEVER** directly authorize or execute a payment.  
> All financial authorization decisions **MUST** pass through the deterministic Policy Engine.

---

## 🏗️ Architecture Overview

- **Frontend**: React 18/19, TypeScript, Vite, Tailwind CSS
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2
- **Database**: PostgreSQL 16 (via Docker Compose)
- **Infrastructure**: Lightweight, simple, hackathon-focused (no unnecessary Redis/Kafka/microservices)

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [Python 3.11+](https://www.python.org/)
- [Node.js 18+ & npm](https://nodejs.org/)

---

### 2. Environment Setup

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

---

### ⚡ Quick Start (All-in-One Command)

To automatically start PostgreSQL, run migrations, and launch both Backend and Frontend in a single terminal:

```bash
./start.sh
```
*(or `npm run dev` or `python3 start.py` from any folder)*

To run end-to-end API & full-stack tests:
```bash
python3 scripts/test_system.py
```

---

### 3. Start PostgreSQL Database

Start the PostgreSQL 16 container:
```bash
docker compose up -d
```

To stop the database:
```bash
docker compose down
```

---

### 4. Backend Setup & Startup

1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run database migrations:
   ```bash
   alembic upgrade head
   ```

5. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

6. Verify the backend health endpoint:
   ```bash
   curl http://127.0.0.1:8000/health
   ```
   Interactive API docs are available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

### 5. Frontend Setup & Startup

1. Open a new terminal and navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the Vite dev server:
   ```bash
   npm run dev
   ```

4. Open the frontend in your browser:
   [http://localhost:5173](http://localhost:5173)

---

### 6. Running Tests

Run the backend test suite:
```bash
cd backend
./.venv/bin/pytest tests -v
```

---

## 🔒 Security & Development Rules

1. **Never store real card numbers.**
2. **Never expose payment secrets to the frontend.**
3. **Never allow LLM to directly execute payments.**
4. **Every payment must pass through the deterministic Policy Engine.**
5. **Every payment must have a unique idempotency key.**
6. **Every payment attempt must create an immutable audit event.**
7. **Fallback payment methods must also pass policy checks.**
8. **Never use live payment credentials during development.**
9. **Never commit `.env` files.**
10. **Keep modules small, typed, and testable.**
