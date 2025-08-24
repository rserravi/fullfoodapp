from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import uuid

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON as SAJSON


class ShoppingItem(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    user_id: str = Field(default="default", index=True)
    name: str = Field(index=True)
    qty: Optional[float] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    checked: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Appliance(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    user_id: str = Field(default="default", index=True)
    name: str = Field(index=True)
    brand: Optional[str] = None
    model: Optional[str] = None
    kind: Optional[str] = Field(default=None, index=True)  # "airfryer" | "horno" | "mambo" | ...
    power_w: Optional[int] = None
    capacity_l: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlanEntry(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    user_id: str = Field(default="default", index=True)
    plan_date: date = Field(index=True)
    meal: str = Field(index=True, description="breakfast|lunch|dinner|snack")
    title: Optional[str] = None
    portions: int = 2
    recipe: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SAJSON))
    appliances: Optional[List[str]] = Field(default=None, sa_column=Column(SAJSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Product(SQLModel, table=True):
    """
    Catálogo de productos (posible por-usuario y/o global).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    user_id: str = Field(default="default", index=True)
    name: str = Field(index=True, description="Nombre canónico en minúsculas (p.ej. 'calabacín')")
    category: Optional[str] = Field(default=None, index=True)  # p.ej. verduras, lácteos, carnes, etc.
    synonyms: Optional[List[str]] = Field(default=None, sa_column=Column(SAJSON))
    is_global: bool = Field(default=False, index=True)  # visible para todos
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KVCache(SQLModel, table=True):
    """
    Cache simple clave/valor por usuario.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    user_id: str = Field(default="default", index=True)
    key: str = Field(index=True)
    value: Dict[str, Any] = Field(sa_column=Column(SAJSON))
    expires_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
