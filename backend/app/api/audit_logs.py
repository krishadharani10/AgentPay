from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogResponse

router = APIRouter(prefix="/api/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=List[AuditLogResponse])
def get_audit_logs(
    agent_id: Optional[UUID] = None,
    decision: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    List audit logs for explainability and audit trail.
    """
    stmt = select(AuditLog)
    if agent_id:
        stmt = stmt.where(AuditLog.agent_id == agent_id)
    if decision:
        stmt = stmt.where(AuditLog.decision == decision.upper())

    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    logs = db.execute(stmt).scalars().all()
    return logs
