from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
import uuid

class ShoppingItem(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    name: str = Field(index=True)
    qty: Optional[float] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    checked: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
