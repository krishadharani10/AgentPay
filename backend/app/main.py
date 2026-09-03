from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.api.health import router as health_router
from app.api.policy import router as policy_router
from app.api.wallet import router as wallet_router
from app.api.policies import router as policies_router
from app.api.merchants import router as merchants_router
from app.api.transactions import router as transactions_router
from app.api.audit_logs import router as audit_logs_router
from app.api.agent import router as agent_router
from app.api.payments import router as payments_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Permissioned payment infrastructure for AI agents",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health_router)
app.include_router(policy_router)
app.include_router(wallet_router)
app.include_router(policies_router)
app.include_router(merchants_router)
app.include_router(transactions_router)
app.include_router(audit_logs_router)
app.include_router(agent_router)
app.include_router(payments_router)



@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "message": "Welcome to AgentPay API",
        "docs": "/docs",
        "health": "/health",
    }
