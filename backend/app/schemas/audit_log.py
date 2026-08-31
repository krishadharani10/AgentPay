from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: Optional[UUID] = None
    transaction_id: Optional[UUID] = None
    event_type: str
    action: str
    decision: str
    reason: str
    rules_checked: Optional[List[Dict[str, Any]]] = None
    metadata_payload: Optional[Dict[str, Any]] = None
    created_at: datetime
