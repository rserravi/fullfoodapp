from typing import List, Dict
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import ShoppingItem, PlanEntry
from ..schemas import RecipePlan, RecipeNeutral, AggregatedItem
from ..services.ingredients import extract_ingredients
from ..services.quantify import extract_and_aggregate
from ..services.catalog import categorize_names
from ..services.cache import make_key, get_payload, set_payload
from ..security import get_current_user
from ..services.cache import make_key, get_payload, set_payload


router = APIRouter(tags=["shopping"])

def week_bounds(start: date):
    monday = start - timedelta(days=start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

@router.get("/shopping-list/aggregate-week", response_model=List[AggregatedItem])
async def aggregate_week(
    start: date = Query(..., description="YYYY-MM-DD"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, sunday = week_bounds(start)
    # <<< clave estable por inicio de semana (lunes) >>>
    cache_key = make_key("agg-week", {"week_start": str(monday)})

    cached = get_payload(session, user_id, cache_key)
    if cached is not None and isinstance(cached, list):
        try:
            return [AggregatedItem(**obj) for obj in cached]
        except Exception:
            pass

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

@router.post("/shopping-list/items-detailed", response_model=List[ShoppingItem])
def add_items_detailed(
    items: List[AggregatedItem] = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    out: List[ShoppingItem] = []
    for a in items:
        name = " ".join(a.name.strip().lower().split())
        existing = session.exec(
            select(ShoppingItem).where(
                ShoppingItem.user_id == user_id, ShoppingItem.name == name
            )
        ).first()
        if not existing:
            it = ShoppingItem(
                user_id=user_id, name=name, qty=a.qty, unit=a.unit, category=a.category
            )
            session.add(it)
            session.commit()
            out.append(it)
        else:
            if existing.qty is not None and a.qty is not None and (existing.unit == a.unit):
                existing.qty = (existing.qty or 0) + a.qty
            else:
                existing.qty = a.qty if a.qty is not None else existing.qty
                existing.unit = a.unit if a.unit is not None else existing.unit
            if a.category:
                existing.category = a.category
            session.add(existing)
            session.commit()
            out.append(existing)
    return out

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

# -------- Agregado semanal (con cache 12h) --------
@router.get("/shopping-list/aggregate-week", response_model=List[AggregatedItem])
async def aggregate_week(
    start: date = Query(..., description="YYYY-MM-DD"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    # Cache lookup
    cache_key = make_key("agg-week", {"start": str(start)})
    cached = get_payload(session, user_id, cache_key)
    if cached is not None and isinstance(cached, list):
        try:
            return [AggregatedItem(**obj) for obj in cached]
        except Exception:
            pass  # si hay algo raro, recalculamos

    monday, sunday = week_bounds(start)
    plans = session.exec(
        select(PlanEntry)
        .where(
            PlanEntry.user_id == user_id,
            PlanEntry.plan_date >= monday,
            PlanEntry.plan_date <= sunday,
        )
    ).all()

    aggregated: List[AggregatedItem] = []
    for p in plans:
        if not p.recipe:
            continue
        try:
            recipe = RecipeNeutral(**p.recipe)
        except Exception:
            continue
        items = await extract_and_aggregate(recipe, session, user_id)
        aggregated.extend(items)

    # Merge final por (name, unit)
    merged: Dict[tuple, AggregatedItem] = {}
    for a in aggregated:
        key = (a.name, a.unit or "ud")
        if key not in merged:
            merged[key] = AggregatedItem(name=a.name, qty=a.qty, unit=a.unit, category=None)
        else:
            if a.qty is not None and merged[key].qty is not None:
                merged[key].qty = (merged[key].qty or 0) + a.qty
            elif a.qty is not None and merged[key].qty is None:
                merged[key].qty = a.qty

    result = list(merged.values())

    # Categorizar
    cat_map = categorize_names(session, user_id, [it.name for it in result])
    for it in result:
        it.category = cat_map.get(it.name, None)

    # Orden amigable
    result.sort(key=lambda x: ((x.category or "zzzz"), x.name))

   # Guardar en cache 12h
    set_payload(session, user_id, cache_key, [r.model_dump() for r in result], ttl_seconds=12*3600)
    return result

@router.post("/shopping-list/build-from-week", response_model=List[ShoppingItem])
async def build_from_week(
    start: date = Query(..., description="YYYY-MM-DD"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    aggr = await aggregate_week(start=start, session=session, user_id=user_id)
    return add_items_detailed(items=aggr, session=session, user_id=user_id)
