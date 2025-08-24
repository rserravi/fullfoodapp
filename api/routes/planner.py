from __future__ import annotations
from typing import List, Dict, Optional
from datetime import date, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlmodel import Session, select

from ..db import get_session
from ..models_db import PlanEntry
from ..schemas import RecipeNeutral, RecipePlan, RecipeGenRequest
from ..config import settings
from ..rag import hybrid_retrieve, build_context
from ..llm import generate_json
from ..compiler.compiler import compile_recipe
from ..utils.json_repair import repair_json_minimal, repair_via_llm
from ..security import get_current_user

router = APIRouter(prefix="/planner", tags=["planner"])

MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"]

def week_bounds(start: Optional[date]) -> (date, date):
    if start is None:
        start = date.today()
    monday = start - timedelta(days=(start.weekday()))
    sunday = monday + timedelta(days=6)
    return monday, sunday

@router.get("/week", response_model=List[PlanEntry])
def get_week(
    start: Optional[date] = Query(default=None, description="Fecha de referencia (YYYY-MM-DD)"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, sunday = week_bounds(start)
    stmt = (
        select(PlanEntry)
        .where(
            PlanEntry.user_id == user_id,
            PlanEntry.plan_date >= monday,
            PlanEntry.plan_date <= sunday,
        )
        .order_by(PlanEntry.plan_date.asc())
    )
    return session.exec(stmt).all()

@router.post("/entries", response_model=PlanEntry)
def add_entry(
    entry: PlanEntry,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    entry.user_id = user_id
    session.add(entry)
    session.commit()
    return entry

@router.patch("/entries/{entry_id}", response_model=PlanEntry)
def patch_entry(
    entry_id: str,
    patch: Dict = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ent = session.get(PlanEntry, entry_id)
    if not ent or ent.user_id != user_id:
        raise HTTPException(404, "Entrada no encontrada")
    allowed = {"plan_date", "meal", "title", "portions", "recipe", "appliances"}
    for k, v in patch.items():
        if k in allowed:
            setattr(ent, k, v)
    session.add(ent)
    session.commit()
    return ent

@router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: str,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    ent = session.get(PlanEntry, entry_id)
    if not ent or ent.user_id != user_id:
        raise HTTPException(404, "Entrada no encontrada")
    session.delete(ent)
    session.commit()
    return {"ok": True}

# --------- Generación de semana ---------

class WeekGenRequest(RecipeGenRequest):
    start_date: date
    days: int = 7
    meals: List[str] = ["lunch", "dinner"]
    persist: bool = True

def _load_prompt_template() -> str:
    tmpl_path = Path(__file__).resolve().parents[1] / "prompts" / "recipe_generation.md"
    if not tmpl_path.exists():
        raise HTTPException(status_code=500, detail=f"No se encuentra la plantilla de prompt en: {tmpl_path}")
    return tmpl_path.read_text(encoding="utf-8")

async def _generate_recipe_neutral(ingredients: List[str], portions: int, dietary: List[str]) -> RecipeNeutral:
    query = ", ".join(ingredients) if ingredients else "receta sencilla"
    hits = await hybrid_retrieve(query, top_k_each=5)
    if not hits:
        raise HTTPException(status_code=404, detail="No hay contexto para RAG; ingesta vacía.")
    context = build_context(hits)
    tmpl = _load_prompt_template()
    prompt = (tmpl
        .replace("{{ingredients}}", ", ".join(ingredients))
        .replace("{{portions}}", str(portions))
        .replace("{{dietary}}", ", ".join(dietary) if dietary else "ninguna")
        .replace("{{context}}", context)
    )
    raw_json = await generate_json(prompt, model=settings.llm_model, temperature=0.2, max_tokens=1200)
    try:
        data = json.loads(raw_json)
    except Exception:
        ok, repaired = repair_json_minimal(raw_json)
        if ok:
            data = json.loads(repaired)
        else:
            repaired_llm = await repair_via_llm(raw_json)
            data = json.loads(repaired_llm)
    return RecipeNeutral(**data)

@router.post("/generate-week", response_model=List[PlanEntry])
async def generate_week(
    req: WeekGenRequest,
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, _ = week_bounds(req.start_date)
    entries: List[PlanEntry] = []
    for day_idx in range(req.days):
        current = monday + (req.start_date - monday) + timedelta(days=day_idx)
        for meal in req.meals:
            recipe = await _generate_recipe_neutral(req.ingredients, req.portions, req.dietary)
            plan = PlanEntry(
                user_id=user_id,
                plan_date=current,
                meal=meal,
                title=recipe.title,
                portions=req.portions,
                recipe=recipe.model_dump(),
                appliances=req.appliances,
            )
            entries.append(plan)

    if req.persist and entries:
        session.add_all(entries)
        session.commit()

    return entries
