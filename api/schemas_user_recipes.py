from __future__ import annotations

from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field as PydField

from .schemas import RecipeNeutral  # ya existente


class UserRecipeCreate(BaseModel):
    title: str
    portions: Optional[int] = None
    tags: Optional[List[str]] = None
    appliances: Optional[List[str]] = None
    recipe: RecipeNeutral
    source: Literal["user", "ai"] = "user"
    public: bool = False


class UserRecipeUpdate(BaseModel):
    title: Optional[str] = None
    portions: Optional[int] = None
    tags: Optional[List[str]] = None
    appliances: Optional[List[str]] = None
    recipe: Optional[RecipeNeutral] = None
    public: Optional[bool] = None


class UserRecipeOut(BaseModel):
    id: str
    user_id: str
    title: str
    portions: Optional[int] = None
    tags: Optional[List[str]] = None
    appliances: Optional[List[str]] = None
    recipe: RecipeNeutral
    source: str
    public: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
