from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import ShoppingItem
from ..schemas import RecipePlan, RecipeNeutral
from ..services.ingredients import extract_ingredients

router = APIRouter(tags=["shopping"])

@router.get("/shopping-list", response_model=List[ShoppingItem])
def list_items(session: Session = Depends(get_session)):
    return session.exec(
        select(ShoppingItem).order_by(ShoppingItem.created_at.desc())
    ).all()

@router.post("/shopping-list/items", response_model=List[ShoppingItem])
def add_items(
    items: List[str] = Body(...),
    session: Session = Depends(get_session),
):
    """
    Crea (o recupera) items por nombre. No suma cantidades en v1; evita duplicados exactos.
    Cuerpo esperado: ["calabacín","pimiento", ...]
    """
    created: List[ShoppingItem] = []
    for raw in items:
        name = " ".join(raw.strip().split())
        if not name:
            continue
        existing = session.exec(
            select(ShoppingItem).where(ShoppingItem.name == name)
        ).first()
        if existing:
            created.append(existing)
            continue
        it = ShoppingItem(name=name)
        session.add(it)
        session.commit()
        session.refresh(it)
        created.append(it)
    return created

@router.post("/shopping-list/from-recipe", response_model=List[ShoppingItem])
def add_from_recipe(
    recipe: RecipeNeutral,
    session: Session = Depends(get_session),
):
    ing = extract_ingredients(recipe)
    return add_items(items=ing, session=session)

@router.post("/shopping-list/from-recipe-plan", response_model=List[ShoppingItem])
def add_from_recipe_plan(
    plan: RecipePlan,
    session: Session = Depends(get_session),
):
    ing = extract_ingredients(plan.recipe)
    return add_items(items=ing, session=session)

@router.patch("/shopping-list/{item_id}", response_model=ShoppingItem)
def update_item(
    item_id: str,
    patch: Dict = Body(...),
    session: Session = Depends(get_session),
):
    """
    Campos soportados: name, qty, unit, category, checked
    """
    it = session.get(ShoppingItem, item_id)
    if not it:
        raise HTTPException(404, "Item no encontrado")
    allowed = {"name", "qty", "unit", "category", "checked"}
    for k, v in patch.items():
        if k in allowed:
            setattr(it, k, v)
    session.add(it)
    session.commit()
    session.refresh(it)
    return it

@router.delete("/shopping-list/{item_id}")
def delete_item(item_id: str, session: Session = Depends(get_session)):
    it = session.get(ShoppingItem, item_id)
    if not it:
        raise HTTPException(404, "Item no encontrado")
    session.delete(it)
    session.commit()
    return {"ok": True}

@router.delete("/shopping-list")
def clear_items(session: Session = Depends(get_session)):
    rows = session.exec(select(ShoppingItem)).all()
    for r in rows:
        session.delete(r)
    session.commit()
    return {"ok": True, "deleted": len(rows)}
