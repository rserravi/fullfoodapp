from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import uuid

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON as SAJSON


class ShoppingItem(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    name: str = Field(index=True)
    qty: Optional[float] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    checked: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Appliance(SQLModel, table=True):
    """
    Electrodoméstico del usuario. 'kind' sugiere el tipo (airfryer, horno, mambo, induccion, etc.)
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    name: str = Field(index=True)          # nombre visible (p.ej. "Cecotec Mambo Touch")
    brand: Optional[str] = None            # marca
    model: Optional[str] = None            # modelo
    kind: Optional[str] = Field(default=None, index=True)  # "airfryer" | "horno" | "mambo" | ...
    power_w: Optional[int] = None
    capacity_l: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlanEntry(SQLModel, table=True):
    """
    Una comida planificada en una fecha (desayuno/comida/cena/snack) con receta embebida.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    plan_date: date = Field(index=True)  # <- renombrado para evitar choque con el tipo 'date'
    meal: str = Field(index=True, description="breakfast|lunch|dinner|snack")
    title: Optional[str] = None
    portions: int = 2
    # Guardamos receta y lista de electrodomésticos como JSON (SQLite lo almacena como TEXT)
    recipe: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SAJSON))
    appliances: Optional[List[str]] = Field(default=None, sa_column=Column(SAJSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
