from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class MerchantBase(BaseModel):
    name: str
    category: str
    description: Optional[str] = None
    website: Optional[str] = None
    is_active: bool = True


class MerchantCreate(MerchantBase):
    pass


class MerchantResponse(MerchantBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
