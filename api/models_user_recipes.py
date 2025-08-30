from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy import Column
from sqlmodel import SQLModel, Field


class UserRecipe(SQLModel, table=True):
    """
    Recetas creadas o guardadas por el usuario.
    Guardamos el objeto RecipeNeutral como JSON en 'recipe'.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    user_id: str = Field(index=True)

    title: str
    portions: Optional[int] = None
    tags: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    appliances: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))

    # RecipeNeutral serializado (dict)
    recipe: Dict[str, Any] = Field(sa_column=Column(JSON))

    # metadata
    source: str = Field(default="user")  # "user" | "ai"
    public: bool = Field(default=False)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)