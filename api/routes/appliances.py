from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import Appliance
from ..security import get_current_user
from ..errors import ErrorResponse

router = APIRouter(prefix="/appliances", tags=["appliances"])

@router.get(
    "",
    response_model=List[Appliance],
    summary="Listar electrodomésticos",
    responses={400: {"model": ErrorResponse}},
)
def list_appliances(
    limit: int = Query(100, ge=1, le=500, example=100),
    offset: int = Query(0, ge=0, example=0),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    return session.exec(
        select(Appliance)
        .where(Appliance.user_id == user_id)
        .order_by(Appliance.created_at.desc())
        .offset(offset).limit(limit)
    ).all()

@router.post(
    "",
    response_model=Appliance,
    summary="Crear electrodoméstico",
    responses={400: {"model": ErrorResponse}},
)
def create_appliance(
    appliance: Appliance = Body(..., examples={
        "mambo": {"summary":"Cecotec Mambo","value":{"name":"Mambo Touch","brand":"Cecotec","kind":"robot_cocina","power_w":1700}}
    }),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    appliance.user_id = user_id
    session.add(appliance); session.commit()
    return appliance

@router.get(
    "/{appliance_id}",
    response_model=Appliance,
    summary="Obtener electrodoméstico",
    responses={404: {"model": ErrorResponse}},
)
def get_appliance(
    appliance_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ap = session.get(Appliance, appliance_id)
    if not ap or ap.user_id != user_id:
        raise HTTPException(404, "Electrodoméstico no encontrado")
    return ap

@router.patch(
    "/{appliance_id}",
    response_model=Appliance,
    summary="Actualizar electrodoméstico",
    responses={404: {"model": ErrorResponse}},
)
def update_appliance(
    appliance_id: str,
    patch: Dict = Body(..., examples={
        "upd": {"summary":"Cambio de nombre","value":{"name":"Mambo Touch 2"}}
    }),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ap = session.get(Appliance, appliance_id)
    if not ap or ap.user_id != user_id:
        raise HTTPException(404, "Electrodoméstico no encontrado")
    allowed = {"name", "brand", "model", "kind", "power_w", "capacity_l", "notes"}
    for k, v in patch.items():
        if k in allowed:
            setattr(ap, k, v)
    session.add(ap); session.commit()
    return ap

@router.delete(
    "/{appliance_id}",
    summary="Borrar electrodoméstico",
    responses={404: {"model": ErrorResponse}},
)
def delete_appliance(
    appliance_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ap = session.get(Appliance, appliance_id)
    if not ap or ap.user_id != user_id:
        raise HTTPException(404, "Electrodoméstico no encontrado")
    session.delete(ap); session.commit()
    return {"ok": True}
