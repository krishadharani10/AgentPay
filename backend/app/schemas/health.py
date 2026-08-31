from pydantic import BaseModel, Field
from typing import Dict, Any, Optional


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    app: str = Field(..., examples=["AgentPay"])
    environment: str = Field(..., examples=["development"])
    database: str = Field(..., examples=["connected"])
    version: str = Field(default="0.1.0", examples=["0.1.0"])
    details: Optional[Dict[str, Any]] = None
