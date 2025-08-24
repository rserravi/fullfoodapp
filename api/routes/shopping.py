from typing import List, Dict
from datetime import date, timedelta
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from ..db import get_session
from ..models_db import ShoppingItem, PlanEntry
from ..schemas import RecipeNeutral, AggregatedItem
from ..services.ingredients import extract_ingredients
from ..services.quantify import extract_and_aggregate
from ..services.catalog import categorize_names
from ..services.cache import make_key, get_payload, set_payload
from ..security import get_current_user
from ..errors import ErrorResponse

router = APIRouter(tags=["shopping"])

def week_bounds(start: date):
    monday = start - timedelta(days=start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

# -------- Listado con paginación --------
@router.get(
    "/shopping-list",
    response_model=List[ShoppingItem],
    summary="Listar items de compra",
    responses={400: {"model": ErrorResponse}},
)
def list_items(
    limit: int = Query(100, ge=1, le=500, example=100),
    offset: int = Query(0, ge=0, example=0),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    stmt = (
        select(ShoppingItem)
        .where(ShoppingItem.user_id == user_id)
        .order_by(ShoppingItem.created_at.desc())
        .offset(offset).limit(limit)
    )
    return session.exec(stmt).all()

# -------- Alta rápida (strings) --------
@router.post("/shopping-list/items", response_model=List[ShoppingItem], summary="Añadir items por nombre")
def add_items(
    items: List[str] = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    created: List[ShoppingItem] = []
    for raw in items:
        name = " ".join(raw.strip().lower().split())
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

# -------- Alta detallada (qty/unit/category) --------
@router.post(
    "/shopping-list/items-detailed",
    response_model=List[ShoppingItem],
    summary="Añadir/merge items detallados (qty/unit/category)",
)
def add_items_detailed(
    items: List[AggregatedItem] = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    out: List[ShoppingItem] = []
    for a in items:
        name = " ".join(a.name.strip().lower().split())
        existing = session.exec(
            select(ShoppingItem).where(ShoppingItem.user_id == user_id, ShoppingItem.name == name)
        ).first()
        if not existing:
            it = ShoppingItem(user_id=user_id, name=name, qty=a.qty, unit=a.unit, category=a.category)
            session.add(it)
            session.commit()
            out.append(it)
        else:
            if existing.qty is not None and a.qty is not None and (existing.unit == a.unit):
                existing.qty = (existing.qty or 0) + a.qty
            else:
                # si cambian unidades o no hay qty previa, sobrescribe con la nueva info
                if a.qty is not None:
                    existing.qty = a.qty
                if a.unit is not None:
                    existing.unit = a.unit
            if a.category:
                existing.category = a.category
            session.add(existing)
            session.commit()
            out.append(existing)
    return out

# -------- Edición / borrado --------
@router.patch("/shopping-list/{item_id}", response_model=ShoppingItem, summary="Actualizar un item")
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

@router.delete("/shopping-list/{item_id}", summary="Borrar un item")
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

@router.delete("/shopping-list", summary="Vaciar lista de la compra")
def clear_items(
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    rows = session.exec(select(ShoppingItem).where(ShoppingItem.user_id == user_id)).all()
    for r in rows:
        session.delete(r)
    session.commit()
    return {"ok": True, "deleted": len(rows)}

# -------- Agregado semanal (con cache) --------
@router.get(
    "/shopping-list/aggregate-week",
    response_model=List[AggregatedItem],
    summary="Agregado semanal de ingredientes",
    description="Agrega ingredientes de las recetas de la semana (por nombre+unidad) y les asigna categoría.",
    responses={200: {"description": "OK", "content": {"application/json": {"examples": {
        "ok": {"summary": "Ejemplo", "value": [
            {"name":"calabacín","qty":2,"unit":"ud","category":"verduras"},
            {"name":"aceite de oliva","qty":30,"unit":"ml","category":"aceites/vinagres"}
        ]}}
    }}}, 400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def aggregate_week(
    start: date = Query(..., description="YYYY-MM-DD", example="2025-08-25"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, sunday = week_bounds(start)
    cache_key = make_key("agg-week", {"week_start": str(monday)})
    cached = get_payload(session, user_id, cache_key)
    if cached is not None and isinstance(cached, list):
        try:
            return [AggregatedItem(**obj) for obj in cached]
        except Exception:
            pass

    plans = session.exec(
        select(PlanEntry).where(
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

    # Merge por (name, unit)
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

    # Cache 12h
    set_payload(session, user_id, cache_key, [r.model_dump() for r in result], ttl_seconds=12*3600)
    return result

# -------- Persistir agregado semanal en lista --------
@router.post(
    "/shopping-list/build-from-week",
    response_model=List[ShoppingItem],
    summary="Persistir agregado en la lista del usuario",
)
async def build_from_week(
    start: date = Query(..., description="YYYY-MM-DD", example="2025-08-25"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    aggr = await aggregate_week(start=start, session=session, user_id=user_id)
    return add_items_detailed(items=aggr, session=session, user_id=user_id)

# -------- Export CSV --------
@router.get(
    "/shopping-list/export.csv",
    summary="Exportar lista de la compra (CSV)",
    responses={200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}},
)
def export_csv(
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    rows = session.exec(
        select(ShoppingItem)
        .where(ShoppingItem.user_id == user_id)
        .order_by(ShoppingItem.category, ShoppingItem.name)
    ).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "qty", "unit", "category", "checked", "created_at"])
    for r in rows:
        writer.writerow([
            r.name,
            r.qty if r.qty is not None else "",
            r.unit or "",
            r.category or "",
            int(r.checked),
            r.created_at.isoformat()
        ])
    buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=shopping_list.csv"}
    return StreamingResponse(iter([buf.read()]), media_type="text/csv", headers=headers)
