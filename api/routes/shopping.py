from typing import List, Dict
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import ShoppingItem, PlanEntry
from ..schemas import RecipePlan, RecipeNeutral, AggregatedItem
from ..services.ingredients import extract_ingredients
from ..services.quantify import extract_and_aggregate  # <---
from ..security import get_current_user

router = APIRouter(tags=["shopping"])

def week_bounds(start: date):
    monday = start - timedelta(days=start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

@router.get("/shopping-list", response_model=List[ShoppingItem])
def list_items(
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    stmt = (
        select(ShoppingItem)
        .where(ShoppingItem.user_id == user_id)
        .order_by(ShoppingItem.created_at.desc())
    )
    return session.exec(stmt).all()

@router.post("/shopping-list/items", response_model=List[ShoppingItem])
def add_items(
    items: List[str] = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    created: List[ShoppingItem] = []
    for raw in items:
        name = " ".join(raw.strip().split())
        if not name:
            continue
        existing = session.exec(
            select(ShoppingItem)
            .where(ShoppingItem.user_id == user_id, ShoppingItem.name == name)
        ).first()
        if existing:
            created.append(existing)
            continue
        it = ShoppingItem(user_id=user_id, name=name)
        session.add(it)
        session.commit()
        created.append(it)
    return created

@router.post("/shopping-list/from-recipe", response_model=List[ShoppingItem])
def add_from_recipe(
    recipe: RecipeNeutral,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ing = extract_ingredients(recipe)
    return add_items(items=ing, session=session, user_id=user_id)

@router.post("/shopping-list/from-recipe-plan", response_model=List[ShoppingItem])
def add_from_recipe_plan(
    plan: RecipePlan,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ing = extract_ingredients(plan.recipe)
    return add_items(items=ing, session=session, user_id=user_id)

@router.patch("/shopping-list/{item_id}", response_model=ShoppingItem)
def update_item(
    item_id: str,
    patch: Dict = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    it = session.get(ShoppingItem, item_id)
    if not it or it.user_id != user_id:
        raise HTTPException(404, "Item no encontrado")
    allowed = {"name", "qty", "unit", "category", "checked"}
    for k, v in patch.items():
        if k in allowed:
            setattr(it, k, v)
    session.add(it)
    session.commit()
    return it

@router.delete("/shopping-list/{item_id}")
def delete_item(
    item_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    it = session.get(ShoppingItem, item_id)
    if not it or it.user_id != user_id:
        raise HTTPException(404, "Item no encontrado")
    session.delete(it)
    session.commit()
    return {"ok": True}

@router.delete("/shopping-list")
def clear_items(
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    rows = session.exec(
        select(ShoppingItem).where(ShoppingItem.user_id == user_id)
    ).all()
    for r in rows:
        session.delete(r)
    session.commit()
    return {"ok": True, "deleted": len(rows)}

# -------- Agregado semanal (con cantidades/unidades) --------
@router.get("/shopping-list/aggregate-week", response_model=List[AggregatedItem])
async def aggregate_week(
    start: date = Query(..., description="YYYY-MM-DD"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, sunday = week_bounds(start)
    plans = session.exec(
        select(PlanEntry)
        .where(
            PlanEntry.user_id == user_id,
            PlanEntry.plan_date >= monday,
            PlanEntry.plan_date <= sunday,
        )
    ).all()

    aggregated: Dict[str, AggregatedItem] = {}

    for p in plans:
        if not p.recipe:
            continue
        try:
            recipe = RecipeNeutral(**p.recipe)
        except Exception:
            continue
        # LLM extraction + normalización + suma
        items = await extract_and_aggregate(recipe)
        for it in items:
            key = (it.name, it.unit or "ud")
            if key not in aggregated:
                aggregated[key] = AggregatedItem(name=it.name, qty=it.qty, unit=it.unit)
            else:
                if it.qty is not None and aggregated[key].qty is not None:
                    aggregated[key].qty = (aggregated[key].qty or 0) + it.qty
                elif it.qty is not None and aggregated[key].qty is None:
                    aggregated[key].qty = it.qty  # adopta qty si antes era None
                else:
                    # ambos None → lo dejamos como None (o podríamos contar uds)
                    pass

    # Ordena por nombre y familia de unidad
    return sorted(aggregated.values(), key=lambda x: (x.name, x.unit or "zzz"))

@router.post("/shopping-list/build-from-week", response_model=List[ShoppingItem])
async def build_from_week(
    start: date = Query(..., description="YYYY-MM-DD"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    aggr = await aggregate_week(start=start, session=session, user_id=user_id)
    names = [a.name for a in aggr]
    return add_items(items=names, session=session, user_id=user_id)
