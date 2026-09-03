from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import get_settings, Settings
from app.database import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Check health status of the AgentPay service and its database."""
    db_status = "connected"
    details = {}
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "disconnected"
        details["db_error"] = str(exc)

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        app=settings.app_name,
        environment=settings.app_env,
        database=db_status,
        version="0.1.0",
        provider=(getattr(settings, "payment_provider", "MOCK") or "MOCK").upper(),
        policy_engine="active",
        details=details if details else None,
    )
