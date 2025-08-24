from __future__ import annotations
from typing import List, Dict, Optional, Set
from datetime import date, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import Response
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
from ..services.cache import make_key, delete_key
from ..errors import ErrorResponse

router = APIRouter(prefix="/planner", tags=["planner"])

MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"]

def week_bounds(start: Optional[date]) -> (date, date):
    if start is None:
        start = date.today()
    monday = start - timedelta(days=(start.weekday()))
    sunday = monday + timedelta(days=6)
    return monday, sunday

def week_cache_key(d: date) -> str:
    monday, _ = week_bounds(d)
    return make_key("agg-week", {"week_start": str(monday)})

@router.get("/week", response_model=List[PlanEntry], summary="Obtener semana", description="Devuelve las entradas del plan de comidas para la semana de la fecha dada (lunes-domingo).")
def get_week(
    start: Optional[date] = Query(default=None, description="Fecha de referencia (YYYY-MM-DD)", example="2025-08-24"),
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

@router.post(
    "/entries",
    response_model=PlanEntry,
    summary="Crear una entrada del planner",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def add_entry(
    entry: PlanEntry = Body(..., examples={
        "simple": {
            "summary": "Entrada mínima",
            "value": {"plan_date": "2025-08-25", "meal": "lunch", "title": "Pasta al pesto", "portions": 2, "recipe": None, "appliances": ["horno"]}
        }
    }),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    entry.user_id = user_id
    session.add(entry); session.commit()
    delete_key(session, user_id, week_cache_key(entry.plan_date))
    return entry

@router.post(
    "/generate-week",
    response_model=List[PlanEntry],
    summary="Generar semana con IA (RAG+Ollama)",
    description="Genera `days`×`meals` recetas y las persiste si `persist=true`.",
    responses={
        200: {"description": "Semana generada", "content": {"application/json": {"examples": {
            "ok": {"summary": "Ejemplo (1 día x 1 comida)", "value": [
                {"plan_date": "2025-08-26", "meal": "dinner", "title": "Pesto clásico", "portions": 2, "recipe": {"title":"Pesto clásico","portions":2,"steps_generic":[{"action":"prep","description":"..."}]}, "appliances":["airfryer"]}
            ]}}
        }}},
        400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}
    },
)
async def generate_week(
    req: "WeekGenRequest",
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
        session.add_all(entries); session.commit()
        touched: Set[str] = set(week_cache_key(e.plan_date) for e in entries)
        for k in touched: delete_key(session, user_id, k)

    return entries

@router.get(
    "/week.ics",
    summary="Exportar semana como iCalendar (.ics)",
    responses={200: {"content": {"text/calendar": {"schema": {"type": "string", "format": "binary"}}}}},
)
def export_week_ics(
    start: Optional[date] = Query(default=None, description="YYYY-MM-DD", example="2025-08-24"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, sunday = week_bounds(start)
    rows = session.exec(
        select(PlanEntry).where(
            PlanEntry.user_id == user_id,
            PlanEntry.plan_date >= monday,
            PlanEntry.plan_date <= sunday,
        ).order_by(PlanEntry.plan_date.asc())
    ).all()

    def ics_date(d: date) -> str:
        return d.strftime("%Y%m%d")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FullFoodApp//Planner//ES",
        "CALSCALE:GREGORIAN"
    ]
    for r in rows:
        dtstart = ics_date(r.plan_date)
        dtend = ics_date(r.plan_date + timedelta(days=1))
        summary = f"{r.meal.capitalize()}: {r.title or 'Sin título'}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{r.id}",
            f"DTSTAMP:{ics_date(r.plan_date)}T000000Z",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{summary}",
            "END:VEVENT"
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"
    return Response(content=ics, media_type="text/calendar")

# --------- Generación interna ---------
class WeekGenRequest(RecipeGenRequest):
    start_date: date
    days: int = 7
    meals: List[str] = ["lunch", "dinner"]
    persist: bool = True
    model_config = {"json_schema_extra": {
        "examples": [
            {
                "summary": "Semana típica",
                "value": {
                    "start_date": "2025-08-25",
                    "days": 7,
                    "meals": ["lunch","dinner"],
                    "ingredients": ["calabacín","pimiento"],
                    "appliances": ["airfryer","horno"],
                    "portions": 2,
                    "dietary": [],
                    "persist": True
                }
            }
        ]
    }}


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
