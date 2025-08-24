from typing import List
from ..schemas import RecipeNeutral, CompiledPlan
from . import rules_airfryer, rules_oven

# Mapa de aparatos soportados → función de compilación
RULES = {
    "airfryer": rules_airfryer.compile_steps,
    "horno": rules_oven.compile_steps,
    "oven": rules_oven.compile_steps,
}

def compile_recipe(recipe: RecipeNeutral, appliances: List[str]) -> List[CompiledPlan]:
    plans: List[CompiledPlan] = []
    for ap in appliances:
        key = ap.lower()
        fn = RULES.get(key)
        if not fn:
            # aparato no soportado en v1, lo saltamos
            continue
        steps = fn(recipe.steps_generic)
        plans.append(CompiledPlan(appliance=ap, steps=steps))
    return plans