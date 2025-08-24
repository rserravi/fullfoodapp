from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import Product
from ..security import get_current_user
from ..services.catalog import BASE_CATEGORIES, categorize_names

router = APIRouter(prefix="/catalog", tags=["catalog"])

@router.get("/categories", response_model=List[str])
def list_categories():
    return BASE_CATEGORIES

@router.get("/products", response_model=List[Product])
def list_products(
    include_global: bool = Query(True),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    stmt = select(Product)
    if include_global:
        stmt = stmt.where((Product.user_id == user_id) | (Product.is_global == True))
    else:
        stmt = stmt.where(Product.user_id == user_id)
    return session.exec(stmt.order_by(Product.created_at.desc())).all()

@router.post("/products", response_model=Product)
def create_product(
    product: Product,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    product.user_id = user_id if not product.is_global else product.user_id
    # normaliza nombre
    product.name = " ".join(product.name.strip().lower().split())
    session.add(product)
    session.commit()
    return product

@router.patch("/products/{product_id}", response_model=Product)
def patch_product(
    product_id: str,
    patch: Dict = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    prod = session.get(Product, product_id)
    if not prod:
        raise HTTPException(404, "Producto no encontrado")
    # sólo dueño (o si es global, de momento no permitimos editar salvo que coincida user)
    if prod.user_id != user_id:
        raise HTTPException(403, "No autorizado")
    allowed = {"name", "category", "synonyms", "is_global"}
    for k, v in patch.items():
        if k in allowed:
            if k == "name" and isinstance(v, str):
                v = " ".join(v.strip().lower().split())
            setattr(prod, k, v)
    session.add(prod)
    session.commit()
    return prod

@router.delete("/products/{product_id}")
def delete_product(
    product_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    prod = session.get(Product, product_id)
    if not prod:
        raise HTTPException(404, "Producto no encontrado")
    if prod.user_id != user_id:
        raise HTTPException(403, "No autorizado")
    session.delete(prod)
    session.commit()
    return {"ok": True}

@router.post("/categorize", response_model=Dict[str, str])
def categorize_endpoint(
    names: List[str] = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    return categorize_names(session, user_id, names)
