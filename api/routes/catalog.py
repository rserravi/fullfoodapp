from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import Product
from ..security import get_current_user
from ..errors import ErrorResponse

router = APIRouter(prefix="/catalog", tags=["catalog"])

@router.get(
    "/products",
    response_model=List[Product],
    summary="Listar productos (catálogo del usuario)",
    responses={400: {"model": ErrorResponse}},
)
def list_products(
    limit: int = Query(200, ge=1, le=1000, example=200),
    offset: int = Query(0, ge=0, example=0),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    return session.exec(
        select(Product)
        .where(Product.user_id == user_id)
        .order_by(Product.category, Product.name)
        .offset(offset).limit(limit)
    ).all()

@router.post(
    "/products",
    response_model=Product,
    summary="Crear producto en catálogo",
)
def create_product(
    prod: Product = Body(..., examples={
        "aceite": {"summary":"Producto con sinónimos","value":{"name":"aceite de oliva","category":"aceites/vinagres","synonyms":["aceite","AOVE"]}}
    }),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    prod.user_id = user_id
    session.add(prod); session.commit()
    return prod

@router.patch(
    "/products/{product_id}",
    response_model=Product,
    summary="Actualizar producto",
    responses={404: {"model": ErrorResponse}},
)
def update_product(
    product_id: str,
    patch: Dict = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    p = session.get(Product, product_id)
    if not p or p.user_id != user_id:
        raise HTTPException(404, "Producto no encontrado")
    allowed = {"name", "category", "synonyms", "is_global"}
    for k, v in patch.items():
        if k in allowed:
            setattr(p, k, v)
    session.add(p); session.commit()
    return p

@router.delete(
    "/products/{product_id}",
    summary="Borrar producto",
    responses={404: {"model": ErrorResponse}},
)
def delete_product(
    product_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    p = session.get(Product, product_id)
    if not p or p.user_id != user_id:
        raise HTTPException(404, "Producto no encontrado")
    session.delete(p); session.commit()
    return {"ok": True}
