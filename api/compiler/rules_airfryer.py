from typing import List, Dict
from ..schemas import StepGeneric, AppliancePlanStep

# Reglas sencillas v1 para Airfryer
DEFAULTS = {
    "preheat_c": 200,
    "cook_c": 190,
    "flip_each_min": 5
}

def compile_steps(steps: List[StepGeneric]) -> List[AppliancePlanStep]:
    plan: List[AppliancePlanStep] = []
    # Precalentado si hay pasos de cocción
    if any(s.action == "cook" for s in steps):
        plan.append(AppliancePlanStep(
            action="preheat",
            temperature_c=DEFAULTS["preheat_c"],
            time_min=3,
            instructions="Precalienta la airfryer a 200°C (3 min)."
        ))
    for s in steps:
        if s.action == "cook":
            t = s.temperature_c or DEFAULTS["cook_c"]
            time = s.time_min or 10
            plan.append(AppliancePlanStep(
                action="cook",
                temperature_c=t,
                time_min=time,
                instructions=f"Cocina a {t}°C durante {time} min. Agita o voltea a mitad de tiempo."
            ))
        elif s.action == "flip":
            plan.append(AppliancePlanStep(
                action="flip",
                temperature_c=None,
                time_min=None,
                instructions="Abre, agita la cesta o voltea las piezas y cierra. Continúa el tiempo restante."
            ))
        elif s.action in ("prep", "season"):
            plan.append(AppliancePlanStep(
                action=s.action,
                temperature_c=None,
                time_min=s.time_min,
                instructions=s.description
            ))
        elif s.action == "rest":
            plan.append(AppliancePlanStep(
                action="rest",
                temperature_c=None,
                time_min=s.time_min or 2,
                instructions="Deja reposar para asentar jugos y temperatura."
            ))
        elif s.action == "serve":
            plan.append(AppliancePlanStep(
                action="serve",
                temperature_c=None,
                time_min=None,
                instructions="Emplata y sirve."
            ))
    return plan
