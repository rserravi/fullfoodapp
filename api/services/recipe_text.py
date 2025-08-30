from __future__ import annotations

from typing import List
from ..schemas import RecipeNeutral


def recipe_to_text(title: str, recipe: RecipeNeutral) -> str:
    """
    Aplana una RecipeNeutral a texto para embedding/recuperación.
    """
    lines: List[str] = []
    lines.append(title.strip())
    if recipe.portions:
        lines.append(f"raciones: {recipe.portions}")
    if recipe.steps_generic:
        for i, st in enumerate(recipe.steps_generic, start=1):
            desc = st.description or st.action or ""
            ings = ", ".join(st.ingredients or [])
            tools = ", ".join(st.tools or [])
            extra = []
            if st.temperature_c is not None:
                extra.append(f"{st.temperature_c}°C")
            if st.time_min is not None:
                extra.append(f"{st.time_min} min")
            if st.speed:
                extra.append(f"vel {st.speed}")
            info = " | ".join([x for x in [desc, ings, tools, " ".join(extra)] if x])
            if info:
                lines.append(f"Paso {i}: {info}")
    return "\n".join(lines)
