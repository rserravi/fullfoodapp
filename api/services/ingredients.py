from typing import List, Iterable
from ..schemas import RecipeNeutral

STOPWORDS = {"sal", "pimienta"}  # ejemplo simple; amplía según gustes

def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())

def extract_ingredients(recipe: RecipeNeutral) -> List[str]:
    """
    Extrae ingredientes de steps_generic, los normaliza y desduplica.
    No intenta estimar cantidades en v1.
    """
    names: List[str] = []
    for step in recipe.steps_generic:
        for ing in (step.ingredients or []):
            n = _norm(ing)
            if not n or n in STOPWORDS:
                continue
            names.append(n)
    # desduplicar preservando orden
    seen = set()
    out: List[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out

def merge_ingredient_lists(*lists: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for lst in lists:
        for n in lst:
            if n not in seen:
                seen.add(n)
                out.append(n)
    return out
