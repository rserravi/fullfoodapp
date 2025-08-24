from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import Appliance

router = APIRouter(prefix="/appliances", tags=["appliances"])

@router.get("", response_model=List[Appliance])
def list_appliances(session: Session = Depends(get_session)):
    return session.exec(select(Appliance).order_by(Appliance.created_at.desc())).all()

@router.post("", response_model=Appliance)
def create_appliance(appliance: Appliance, session: Session = Depends(get_session)):
    # Permitir id custom si viene; si no, SQLModel genera uno
    session.add(appliance)
    session.commit()
    session.refresh(appliance)
    return appliance

@router.get("/{appliance_id}", response_model=Appliance)
def get_appliance(appliance_id: str, session: Session = Depends(get_session)):
    ap = session.get(Appliance, appliance_id)
    if not ap:
        raise HTTPException(404, "Electrodoméstico no encontrado")
    return ap

@router.patch("/{appliance_id}", response_model=Appliance)
def update_appliance(
    appliance_id: str,
    patch: Dict = Body(...),
    session: Session = Depends(get_session),
):
    ap = session.get(Appliance, appliance_id)
    if not ap:
        raise HTTPException(404, "Electrodoméstico no encontrado")
    allowed = {"name", "brand", "model", "kind", "power_w", "capacity_l", "notes"}
    for k, v in patch.items():
        if k in allowed:
            setattr(ap, k, v)
    session.add(ap)
    session.commit()
    session.refresh(ap)
    return ap

@router.delete("/{appliance_id}")
def delete_appliance(appliance_id: str, session: Session = Depends(get_session)):
    ap = session.get(Appliance, appliance_id)
    if not ap:
        raise HTTPException(404, "Electrodoméstico no encontrado")
    session.delete(ap)
    session.commit()
    return {"ok": True}
