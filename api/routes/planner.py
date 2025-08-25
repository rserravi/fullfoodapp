from __future__ import annotations

from typing import List, Dict, Any
from datetime import date, timedelta, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Body, HTTPException, Query
from pydantic import BaseModel, Field, AliasChoices, ConfigDict

from sqlmodel import Session, select

from ..db import get_session
from ..security import get_current_user
from ..config import settings
from ..schemas import RecipeNeutral  # ✅ NO importamos RecipePlan
from ..models_db import PlanEntry

# Reutilizamos utilidades del generador para mantener prompts/estilo coherentes
from .generate import (
    RecipeGenRequest,
    _build_query as build_query,
    _format_context as format_context,
    _render_prompt as render_prompt,
    _extract_json as extract_json,
    _call_llm as call_llm,
)

from ..embeddings import embed_dual
from ..vectorstore import search

router = APIRouter(tags=["planner"], prefix="/planner")


# ------------------------------------------------------
# Utilidades
# ------------------------------------------------------
def week_bounds(start: date):
    monday = start - timedelta(days=start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _fix_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Asegura time_min > 0 y valores básicos válidos."""
    fixed: List[Dict[str, Any]] = []
    for s in steps or []:
        action = s.get("action") or "step"
        desc = s.get("description") or "Paso"
        ingredients = s.get("ingredients") or []
        tools = s.get("tools") or []
        temp = s.get("temperature_c", None)
        tmin = s.get("time_min", None)
        # normaliza time_min a entero >= 1
        try:
            tmin = int(tmin) if tmin is not None else 5
        except Exception:
            tmin = 5
        if tmin < 1:
            tmin = 5
        fixed.append(
            {
                "action": str(action),
                "description": str(desc),
                "ingredients": [str(x) for x in ingredients],
                "tools": [str(x) for x in tools],
                "temperature_c": int(temp) if isinstance(temp, (int, float)) else None,
                "time_min": tmin,
                "speed": s.get("speed", None),
                "notes": s.get("notes", None),
                "batching": bool(s.get("batching", False)),
            }
        )
    return fixed


def _seed_pool(dietary: List[str], sin_gluten: bool) -> List[List[str]]:
    """Conjunto de semillas de ingredientes rotatorias, ajustadas por preferencias."""
    lower = {d.lower() for d in dietary}
    veg = ("vegetariano" in lower) or ("vegano" in lower)
    if veg:
        base = [
            ["garbanzos", "espinacas", "tomate"],
            ["pasta sin huevo" if sin_gluten else "pasta", "calabacín", "queso"],
            ["lentejas", "zanahoria", "cebolla"],
            ["tofu", "brócoli", "soja"],
            ["arroz", "pimientos", "maíz"],
            ["quinoa", "setas", "calabaza"],
            ["berenjena", "tomate", "albahaca"],
        ]
    else:
        base = [
            ["pollo", "pimientos", "arroz"],
            ["garbanzos", "espinacas", "tomate"],
            ["pasta", "calabacín", "queso"],
            ["huevos", "patata", "cebolla"],
            ["salmón", "brócoli", "limón"],
            ["lentejas", "zanahoria", "cebolla"],
            ["ternera", "pimientos", "fideos"],
        ]

    if sin_gluten:
        def swap_gluten(trip: List[str]) -> List[str]:
            return [
                "arroz" if x in {"pasta", "fideos", "pasta sin huevo"} else x
                for x in trip
            ]
        base = [swap_gluten(t) for t in base]
    return base


async def _generate_recipe_neutral(
    ingredients: List[str],
    portions: int,
    appliances: List[str],
    dietary: List[str],
    top_k: int = 5,
    mode: str = "hybrid",
) -> RecipeNeutral:
    """Genera una receta RecipeNeutral reutilizando el pipeline del generador (RAG + prompts de /api/prompts)."""
    gen_req = RecipeGenRequest(
        ingredients=ingredients,
        portions=portions,
        appliances=appliances,
        dietary=dietary,
        top_k=top_k,
        mode=mode,  # "hybrid" por defecto
    )

    # 1) Embeddings de la consulta
    query = build_query(gen_req)
    emb = await embed_dual([query])

    # 2) Vectores válidos para Qdrant
    dims = settings.parsed_vector_dims()
    query_vectors: Dict[str, List[float]] = {}
    for key in dims.keys():  # p.ej. "mxbai", "jina"
        vecs = emb.get(key) or []
        if vecs and isinstance(vecs[0], list) and len(vecs[0]) == dims[key]:
            query_vectors[key] = vecs[0]
    if not query_vectors:
        raise HTTPException(500, "Fallo preparando embeddings de búsqueda (no hay vectores válidos).")

    # 3) Búsqueda RAG
    hits = search(query_vectors, top_k=top_k)

    # 4) Prompt desde plantilla y llamada LLM
    context = format_context(hits)
    prompt = render_prompt(gen_req, context)
    raw = await call_llm(prompt)

    # 5) Parseo/validación y fixes mínimos
    try:
        data = extract_json(raw)
        recipe = RecipeNeutral(
            title=str(data.get("title") or "Receta"),
            portions=int(data.get("portions") or portions),
            steps_generic=_fix_steps(data.get("steps_generic") or []),
        )
    except Exception:
        # Fallback seguro si el modelo devuelve algo fuera de formato
        recipe = RecipeNeutral(
            title="Receta generada",
            portions=portions,
            steps_generic=_fix_steps(
                [
                    {
                        "action": "prep",
                        "description": "Preparar ingredientes básicos.",
                        "ingredients": [*ingredients],
                        "tools": [],
                        "temperature_c": None,
                        "time_min": 5,
                        "speed": None,
                        "notes": "Fallback: estructura inválida del modelo.",
                        "batching": False,
                    },
                    {
                        "action": "cook",
                        "description": "Cocinar con el electrodoméstico disponible más conveniente.",
                        "ingredients": [*ingredients],
                        "tools": appliances[:1] if appliances else [],
                        "temperature_c": 190 if ("airfryer" in appliances) else None,
                        "time_min": 12,
                        "speed": None,
                        "notes": None,
                        "batching": False,
                    },
                ]
            ),
        )

    return recipe


# ------------------------------------------------------
# Modelos de petición/respuesta
# ------------------------------------------------------
class WeekGenRequest(BaseModel):
    """Petición de plan semanal; acepta 'start' o 'start_date' en el body."""
    model_config = ConfigDict(populate_by_name=True)

    start: date = Field(
        ...,
        description="Fecha de inicio de la semana (YYYY-MM-DD). Acepta 'start' o 'start_date'.",
        validation_alias=AliasChoices("start", "start_date"),
        serialization_alias="start",
        examples=["2025-08-25"],
    )
    portions: int = Field(2, ge=1, le=12, description="Raciones por receta")
    appliances: List[str] = Field(default_factory=list, description="Electrodomésticos disponibles")
    dietary: List[str] = Field(default_factory=list, description="Preferencias/restricciones")
    persist: bool = Field(True, description="Si true, persiste el plan generado")


class RecipePlanOut(BaseModel):
    """Ítem de plan (una comida en un día)."""
    plan_date: date
    meal: str
    portions: int
    appliances: List[str] = []
    title: str
    id: str
    recipe: RecipeNeutral
    created_at: datetime


# ------------------------------------------------------
# Endpoints
# ------------------------------------------------------
@router.post(
    "/generate-week",
    summary="Generar plan semanal (1 cena/día, modo híbrido con RAG)",
    response_model=List[RecipePlanOut],
)
async def generate_week(
    req: WeekGenRequest = Body(...),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, _ = week_bounds(req.start)

    # Construye una rotación de semillas de ingredientes
    sin_gluten = any("sin gluten" == d.lower() for d in req.dietary)
    seeds = _seed_pool(req.dietary, sin_gluten)

    results: List[RecipePlanOut] = []
    for i in range(7):
        plan_date = monday + timedelta(days=i)
        seed = seeds[i % len(seeds)]

        # Genera receta anclada al RAG (modo híbrido)
        recipe = await _generate_recipe_neutral(
            ingredients=seed,
            portions=req.portions,
            appliances=req.appliances,
            dietary=req.dietary,
            top_k=5,
            mode="hybrid",
        )

        # Crea el objeto de respuesta (y opcionalmente persistimos)
        title = recipe.title or "Receta"
        rid = str(uuid4())

        if req.persist:
            entry = PlanEntry(
                id=rid,
                user_id=user_id,
                plan_date=plan_date,
                meal="dinner",
                portions=req.portions,
                appliances=req.appliances,
                title=title,
                recipe=recipe.model_dump(),
                created_at=datetime.utcnow(),
            )
            session.add(entry)

        results.append(
            RecipePlanOut(
                plan_date=plan_date,
                meal="dinner",
                portions=req.portions,
                appliances=req.appliances,
                title=title,
                id=rid,
                recipe=recipe,
                created_at=datetime.utcnow(),
            )
        )

    if req.persist:
        session.commit()

    return results


@router.get(
    "/week",
    summary="Listar plan semanal existente",
    response_model=List[RecipePlanOut],
)
def get_week(
    start: date = Query(..., description="YYYY-MM-DD (inicio de semana)"),
    session: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    monday, sunday = week_bounds(start)
    rows = session.exec(
        select(PlanEntry).where(
            PlanEntry.user_id == user_id,
            PlanEntry.plan_date >= monday,
            PlanEntry.plan_date <= sunday,
        ).order_by(PlanEntry.plan_date)
    ).all()

    out: List[RecipePlanOut] = []
    for r in rows:
        try:
            recipe = RecipeNeutral(**(r.recipe or {}))
        except Exception:
            recipe = RecipeNeutral(title=r.title or "Receta", portions=r.portions or 2, steps_generic=[])
        out.append(
            RecipePlanOut(
                plan_date=r.plan_date,
                meal=r.meal,
                portions=r.portions,
                appliances=r.appliances or [],
                title=r.title or recipe.title,
                id=r.id,
                recipe=recipe,
                created_at=r.created_at,
            )
        )
    return out
